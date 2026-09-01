from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import PurePath
import re
from uuid import UUID, uuid4

from psycopg import AsyncConnection, Error as PsycopgError
from psycopg.types.json import Jsonb
from vercel.blob import AsyncBlobClient, BlobError

from app.core.config import Settings
from app.models.schemas import (
    AnalysisResult,
    ApplicantInput,
    DocumentExtraction,
    EvidenceCategory,
    Product,
)


class DocumentPersistenceError(RuntimeError):
    def __init__(self, stage: str, *, partial: bool) -> None:
        super().__init__(f"document persistence failed during {stage}")
        self.stage = stage
        self.partial = partial


class PersistenceReadError(RuntimeError):
    pass


class PersistenceClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def save_applicant(self, data: ApplicantInput) -> bool:
        if not self.settings.database_configured or data.session_id is None:
            return False
        try:
            async with self._connection() as connection:
                await connection.execute(
                    "insert into users (id) values (%s) on conflict (id) do nothing",
                    (data.session_id,),
                )
                await connection.execute(
                    """
                    insert into evidences (user_id, payload, self_reported_risk, simulation_input)
                    values (%s, %s, %s, true)
                    """,
                    (
                        data.session_id,
                        Jsonb(data.model_dump(mode="json", exclude={"session_id"})),
                        data.self_reported_risk,
                    ),
                )
            return True
        except PsycopgError:
            return False

    async def save_document(
        self,
        *,
        user_id: UUID,
        category: EvidenceCategory,
        filename: str,
        content_type: str,
        content: bytes,
        extraction: DocumentExtraction,
    ) -> UUID | None:
        if not self.settings.database_configured and not self.settings.blob_read_write_token:
            return None
        if not self.settings.document_storage_configured:
            raise DocumentPersistenceError("configuration", partial=False)

        upload_id = uuid4()
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", PurePath(filename).name)[:100] or "document"
        pathname = f"evidences/{user_id}/{upload_id}/{safe_name}"

        async with AsyncBlobClient(token=self.settings.blob_read_write_token) as blob_client:
            try:
                uploaded = await blob_client.put(
                    pathname,
                    content,
                    access="private",
                    content_type=content_type,
                )
            except BlobError as error:
                raise DocumentPersistenceError("storage", partial=False) from error

            statements_complete = False
            try:
                async with self._connection() as connection:
                    await connection.execute(
                        "insert into users (id) values (%s) on conflict (id) do nothing",
                        (user_id,),
                    )
                    await connection.execute(
                        """
                        insert into document_uploads (
                            id, user_id, category, storage_url, extracted_fields, extraction_status
                        ) values (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            upload_id,
                            user_id,
                            category.value,
                            uploaded.url,
                            Jsonb(extraction.fields),
                            extraction.status,
                        ),
                    )
                    statements_complete = True
                return upload_id
            except PsycopgError as error:
                if statements_complete:
                    if await self._document_exists(upload_id):
                        return upload_id
                    raise DocumentPersistenceError("metadata", partial=True) from error
                await self._delete_blob(blob_client, uploaded.url)
                raise DocumentPersistenceError("metadata", partial=False) from error
            except Exception as error:
                if statements_complete:
                    raise DocumentPersistenceError("metadata", partial=True) from error
                await self._delete_blob(blob_client, uploaded.url)
                raise DocumentPersistenceError("metadata", partial=False) from error
            except BaseException:
                if not statements_complete:
                    try:
                        await blob_client.delete(uploaded.url)
                    except BlobError:
                        pass
                raise

    async def save_report(self, user_id: UUID | None, result: AnalysisResult) -> bool:
        if not self.settings.database_configured or user_id is None:
            return False
        try:
            async with self._connection() as connection:
                await connection.execute(
                    """
                    insert into credit_reports (
                        id, user_id, evidence_strength, evidence_level, summary,
                        risk_alert, risk_alert_message, payload
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        result.report_id,
                        user_id,
                        result.evidence_strength,
                        result.evidence_level,
                        result.summary,
                        result.risk_alert.active,
                        result.risk_alert.message,
                        Jsonb(result.model_dump(mode="json")),
                    ),
                )
                if result.items:
                    async with connection.cursor() as cursor:
                        await cursor.executemany(
                            """
                            insert into report_items (
                                report_id, item_key, title, value, strength, explanation, source
                            ) values (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            [
                                (
                                    result.report_id,
                                    item.key,
                                    item.title,
                                    item.value,
                                    item.strength,
                                    item.explanation,
                                    item.source,
                                )
                                for item in result.items
                            ],
                        )
            return True
        except PsycopgError:
            return False

    async def get_report(self, report_id: UUID, user_id: UUID) -> AnalysisResult | None:
        if not self.settings.database_configured:
            return None
        try:
            async with self._connection() as connection:
                cursor = await connection.execute(
                    "select payload from credit_reports where id = %s and user_id = %s",
                    (report_id, user_id),
                )
                row = await cursor.fetchone()
            return AnalysisResult.model_validate(row[0]) if row else None
        except (PsycopgError, TypeError, ValueError) as error:
            raise PersistenceReadError("report lookup failed") from error

    async def get_active_products(self) -> list[Product]:
        if not self.settings.database_configured:
            return []
        try:
            async with self._connection() as connection:
                cursor = await connection.execute(
                    """
                    select
                        name, provider, category, eligible_visas, limit_text, rate_text,
                        requirement_text, source_url, verified_at::text
                    from matched_products
                    where is_active = true
                    order by category, provider, name
                    """,
                    (),
                )
                rows = await cursor.fetchall()
            return [
                Product(
                    name=row[0],
                    provider=row[1],
                    category=row[2],
                    eligible_visas=row[3],
                    limit_text=row[4],
                    rate_text=row[5],
                    requirement_text=row[6],
                    source_url=row[7],
                    verified_at=row[8],
                    match_reason="",
                )
                for row in rows
            ]
        except (PsycopgError, TypeError, ValueError) as error:
            raise PersistenceReadError("product lookup failed") from error

    async def get_document_categories(self, user_id: UUID | None) -> list[EvidenceCategory]:
        if not self.settings.database_configured or user_id is None:
            return []
        try:
            async with self._connection() as connection:
                cursor = await connection.execute(
                    """
                    select distinct category
                    from document_uploads
                    where user_id = %s and extraction_status = 'extracted'
                    order by category
                    """,
                    (user_id,),
                )
                rows = await cursor.fetchall()
            return [EvidenceCategory(row[0]) for row in rows]
        except (PsycopgError, ValueError) as error:
            raise PersistenceReadError("document lookup failed") from error

    async def _document_exists(self, upload_id: UUID) -> bool:
        try:
            async with self._connection() as connection:
                cursor = await connection.execute(
                    "select 1 from document_uploads where id = %s",
                    (upload_id,),
                )
                return await cursor.fetchone() is not None
        except PsycopgError:
            return False

    @staticmethod
    async def _delete_blob(blob_client: AsyncBlobClient, url: str) -> None:
        try:
            await blob_client.delete(url)
        except BlobError as error:
            raise DocumentPersistenceError("cleanup", partial=True) from error

    async def _connect(self) -> AsyncConnection:
        timeout_seconds = max(1, round(self.settings.request_timeout_seconds))
        return await AsyncConnection.connect(
            self.settings.database_url,
            connect_timeout=timeout_seconds,
        )

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[AsyncConnection]:
        connection = await self._connect()
        try:
            async with connection:
                timeout_ms = max(1, round(self.settings.request_timeout_seconds)) * 1000
                await connection.execute(f"set local statement_timeout = {timeout_ms}", ())
                yield connection
        finally:
            await connection.close()

import asyncio
from io import BytesIO
from types import TracebackType
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from psycopg import OperationalError
from vercel.blob import BlobError

from app.api.documents import MULTIPART_OVERHEAD_BYTES
from app.core.config import Settings
from app.main import app
from app.models.schemas import (
    AnalysisResult,
    DocumentExtraction,
    EvidenceCategory,
    EvidenceItem,
    Product,
    RiskAlert,
)
from app.services.persistence_client import (
    DocumentPersistenceError,
    PersistenceClient,
    PersistenceReadError,
)


def settings() -> Settings:
    return Settings(
        database_url="postgresql://test.invalid/database?sslmode=require",
        blob_read_write_token="test-blob-token",
        kosis_api_key="",
        exim_exchange_api_key="",
        llm_api_key="",
        llm_model="",
        llm_api_base_url="",
        frontend_origin="http://localhost:5173",
    )


def extraction() -> DocumentExtraction:
    return DocumentExtraction(
        category=EvidenceCategory.EMPLOYMENT,
        status="extracted",
        fields={"employment_months": 12},
    )


class FakeResult:
    def __init__(self, rows: list[tuple[object, ...]] | None = None) -> None:
        self.rows = rows or []

    async def fetchone(self) -> tuple[object, ...] | None:
        return self.rows[0] if self.rows else None

    async def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


class FakeBatchCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeBatchCursor":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def executemany(self, query: str, params: list[tuple[object, ...]]) -> None:
        self.connection.statements.append(" ".join(query.split()))
        self.connection.batch_size = len(params)
        if self.connection.fail_report_items:
            raise OperationalError("report item insert failed")


class FakeConnection:
    def __init__(
        self,
        *,
        rows: list[tuple[object, ...]] | None = None,
        fail_document_insert: bool = False,
        fail_report_items: bool = False,
        fail_commit: bool = False,
    ) -> None:
        self.rows = rows or []
        self.fail_document_insert = fail_document_insert
        self.fail_report_items = fail_report_items
        self.fail_commit = fail_commit
        self.statements: list[str] = []
        self.batch_size = 0
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.committed = exc_type is None
        self.rolled_back = exc_type is not None
        if exc_type is None and self.fail_commit:
            raise OperationalError("commit response lost")

    async def execute(self, query: str, params: tuple[object, ...]) -> FakeResult:
        compact_query = " ".join(query.split())
        self.statements.append(compact_query)
        if self.fail_document_insert and "insert into document_uploads" in compact_query:
            raise OperationalError("document insert failed")
        return FakeResult(self.rows)

    def cursor(self) -> FakeBatchCursor:
        return FakeBatchCursor(self)

    async def close(self) -> None:
        self.closed = True


class FakeBlobClient:
    def __init__(self, *, cleanup_fails: bool = False) -> None:
        self.url = "https://blob.example/evidence"
        self.deleted: list[str] = []
        self.cleanup_fails = cleanup_fails

    async def __aenter__(self) -> "FakeBlobClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def put(
        self,
        path: str,
        body: bytes,
        *,
        access: str,
        content_type: str,
    ) -> object:
        self.path = path
        self.body = body
        self.access = access
        self.content_type = content_type
        return type("UploadedBlob", (), {"url": self.url})()

    async def delete(self, url: str) -> None:
        self.deleted.append(url)
        if self.cleanup_fails:
            raise BlobError("cleanup failed")


class StorageTest(unittest.IsolatedAsyncioTestCase):
    async def test_database_timeout_is_set_inside_the_transaction(self) -> None:
        connection = FakeConnection()
        client = PersistenceClient(settings())

        with patch(
            "app.services.persistence_client.AsyncConnection.connect",
            AsyncMock(return_value=connection),
        ) as connect:
            async with client._connection():
                pass

        self.assertNotIn("options", connect.await_args.kwargs)
        self.assertEqual(connection.statements, ["set local statement_timeout = 8000"])

    async def test_active_products_are_loaded_with_text_date(self) -> None:
        connection = FakeConnection(
            rows=[
                (
                    "하나 외국인 EZ Loan",
                    "하나은행",
                    "시중은행_외국인신용대출",
                    ["E-7", "E-9"],
                    "100만~1,000만원",
                    None,
                    "공개 조건",
                    "https://example.com/product",
                    "2026-09-01",
                )
            ]
        )
        client = PersistenceClient(settings())

        with patch.object(client, "_connect", AsyncMock(return_value=connection)):
            products = await client.get_active_products()

        self.assertEqual(
            products,
            [
                Product(
                    name="하나 외국인 EZ Loan",
                    provider="하나은행",
                    category="시중은행_외국인신용대출",
                    eligible_visas=["E-7", "E-9"],
                    limit_text="100만~1,000만원",
                    requirement_text="공개 조건",
                    source_url="https://example.com/product",
                    verified_at="2026-09-01",
                    match_reason="",
                )
            ],
        )
        self.assertTrue(any("where is_active = true" in statement for statement in connection.statements))
        self.assertTrue(any("verified_at::text" in statement for statement in connection.statements))

    async def test_only_extracted_documents_become_verified_categories(self) -> None:
        connection = FakeConnection(rows=[("employment",), ("telecom",)])
        client = PersistenceClient(settings())

        with patch.object(client, "_connect", AsyncMock(return_value=connection)):
            categories = await client.get_document_categories(uuid4())

        self.assertEqual(categories, [EvidenceCategory.EMPLOYMENT, EvidenceCategory.TELECOM])
        self.assertTrue(
            any("extraction_status = 'extracted'" in statement for statement in connection.statements)
        )

    async def test_blob_is_deleted_when_document_insert_fails(self) -> None:
        connection = FakeConnection(fail_document_insert=True)
        blob = FakeBlobClient()
        client = PersistenceClient(settings())

        with (
            patch.object(client, "_connect", AsyncMock(return_value=connection)),
            patch("app.services.persistence_client.AsyncBlobClient", return_value=blob),
            self.assertRaises(DocumentPersistenceError) as raised,
        ):
            await client.save_document(
                user_id=uuid4(),
                category=EvidenceCategory.EMPLOYMENT,
                filename="evidence.png",
                content_type="image/png",
                content=b"image",
                extraction=extraction(),
            )

        self.assertEqual(raised.exception.stage, "metadata")
        self.assertFalse(raised.exception.partial)
        self.assertEqual(blob.deleted, [blob.url])
        self.assertTrue(connection.rolled_back)

    async def test_blob_cleanup_failure_is_reported_as_partial(self) -> None:
        connection = FakeConnection(fail_document_insert=True)
        blob = FakeBlobClient(cleanup_fails=True)
        client = PersistenceClient(settings())

        with (
            patch.object(client, "_connect", AsyncMock(return_value=connection)),
            patch("app.services.persistence_client.AsyncBlobClient", return_value=blob),
            self.assertRaises(DocumentPersistenceError) as raised,
        ):
            await client.save_document(
                user_id=uuid4(),
                category=EvidenceCategory.EMPLOYMENT,
                filename="evidence.png",
                content_type="image/png",
                content=b"image",
                extraction=extraction(),
            )

        self.assertEqual(raised.exception.stage, "cleanup")
        self.assertTrue(raised.exception.partial)

    async def test_ambiguous_commit_preserves_blob_and_reports_partial_failure(self) -> None:
        write_connection = FakeConnection(fail_commit=True)
        verification_connection = FakeConnection()
        blob = FakeBlobClient()
        client = PersistenceClient(settings())

        with (
            patch.object(
                client,
                "_connect",
                AsyncMock(side_effect=[write_connection, verification_connection]),
            ),
            patch("app.services.persistence_client.AsyncBlobClient", return_value=blob),
            self.assertRaises(DocumentPersistenceError) as raised,
        ):
            await client.save_document(
                user_id=uuid4(),
                category=EvidenceCategory.EMPLOYMENT,
                filename="evidence.png",
                content_type="image/png",
                content=b"image",
                extraction=extraction(),
            )

        self.assertEqual(raised.exception.stage, "metadata")
        self.assertTrue(raised.exception.partial)
        self.assertEqual(blob.deleted, [])
        self.assertTrue(write_connection.closed)

    async def test_cancellation_before_commit_deletes_uploaded_blob(self) -> None:
        blob = FakeBlobClient()
        client = PersistenceClient(settings())

        with (
            patch.object(client, "_connect", AsyncMock(side_effect=asyncio.CancelledError())),
            patch("app.services.persistence_client.AsyncBlobClient", return_value=blob),
            self.assertRaises(asyncio.CancelledError),
        ):
            await client.save_document(
                user_id=uuid4(),
                category=EvidenceCategory.EMPLOYMENT,
                filename="evidence.png",
                content_type="image/png",
                content=b"image",
                extraction=extraction(),
            )

        self.assertEqual(blob.deleted, [blob.url])

    async def test_database_read_failure_is_not_empty_evidence(self) -> None:
        client = PersistenceClient(settings())
        with (
            patch.object(client, "_connect", AsyncMock(side_effect=OperationalError("database unavailable"))),
            self.assertRaises(PersistenceReadError),
        ):
            await client.get_document_categories(uuid4())

    async def test_report_item_failure_rolls_back_entire_transaction(self) -> None:
        connection = FakeConnection(fail_report_items=True)
        client = PersistenceClient(settings())
        result = AnalysisResult(
            report_id=uuid4(),
            evidence_strength=0,
            evidence_level="추가 자료 필요",
            summary="summary",
            items=[
                EvidenceItem(
                    key="employment",
                    title="재직",
                    value="12개월",
                    strength="moderate",
                    explanation="입력 범위에서 확인했습니다.",
                    source="사용자 입력",
                )
            ],
            risk_alert=RiskAlert(active=False),
            external_metrics=[],
            matched_products=[],
        )

        with patch.object(client, "_connect", AsyncMock(return_value=connection)):
            saved = await client.save_report(uuid4(), result)

        self.assertFalse(saved)
        self.assertTrue(connection.rolled_back)
        self.assertFalse(connection.committed)
        self.assertEqual(connection.batch_size, 1)


class StorageApiTest(unittest.TestCase):
    client = TestClient(app)

    def test_content_length_is_rejected_before_multipart_parsing(self) -> None:
        response = self.client.post(
            "/api/documents",
            content=b"not-a-multipart-body",
            headers={
                "Content-Type": "multipart/form-data; boundary=test",
                "Content-Length": str(app.state.settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES + 1),
            },
        )

        self.assertEqual(response.status_code, 413)

    def test_partial_storage_failure_is_explicit(self) -> None:
        original_llm = app.state.llm
        original_persistence = app.state.persistence

        class StubLlm:
            async def extract_document(
                self,
                category: EvidenceCategory,
                content: bytes,
                content_type: str,
            ) -> DocumentExtraction:
                return extraction()

        class PartialPersistence:
            async def save_document(self, **kwargs: object) -> None:
                raise DocumentPersistenceError("cleanup", partial=True)

        app.state.llm = StubLlm()
        app.state.persistence = PartialPersistence()
        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), "white").save(image_buffer, format="PNG")
        try:
            response = self.client.post(
                "/api/documents",
                data={"session_id": str(uuid4()), "category": "employment"},
                files={"file": ("evidence.png", image_buffer.getvalue(), "image/png")},
            )
        finally:
            app.state.llm = original_llm
            app.state.persistence = original_persistence

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["code"], "document_storage_partial")
        self.assertTrue(response.json()["detail"]["partial"])


if __name__ == "__main__":
    unittest.main()

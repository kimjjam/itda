from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from app.models.schemas import DocumentExtraction, EvidenceCategory
from app.services.persistence_client import DocumentPersistenceError


router = APIRouter(prefix="/documents", tags=["documents"])
ALLOWED_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
MULTIPART_OVERHEAD_BYTES = 64 * 1024


@router.post("", response_model=DocumentExtraction)
async def extract_document(
    request: Request,
    session_id: Annotated[UUID, Form()],
    category: Annotated[EvidenceCategory, Form()],
    file: Annotated[UploadFile, File()],
) -> DocumentExtraction:
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "JPG, PNG, WEBP, PDF 파일만 지원합니다.")

    content = await file.read(request.app.state.settings.max_upload_bytes + 1)
    await file.close()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "빈 파일은 업로드할 수 없습니다.")
    if len(content) > request.app.state.settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "파일은 10MB 이하여야 합니다.")

    extraction = await request.app.state.llm.extract_document(category, content, content_type)
    try:
        upload_id = await request.app.state.persistence.save_document(
            user_id=session_id,
            category=category,
            filename=file.filename or "document",
            content_type=content_type,
            content=content,
            extraction=extraction,
        )
    except DocumentPersistenceError as error:
        detail = {
            "code": "document_storage_partial" if error.partial else "document_storage_failed",
            "message": (
                "문서 메타데이터 저장과 업로드 객체 정리를 완료하지 못했습니다."
                if error.partial
                else "문서를 안전하게 저장하지 못했습니다. 다시 시도해 주세요."
            ),
            "partial": error.partial,
            "stage": error.stage,
        }
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from error
    return extraction.model_copy(update={"upload_id": upload_id})

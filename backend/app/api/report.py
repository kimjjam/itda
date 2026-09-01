from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.models.schemas import AnalysisResult
from app.services.persistence_client import PersistenceReadError


router = APIRouter(prefix="/report", tags=["report"])


@router.get("/{report_id}", response_model=AnalysisResult)
async def report(report_id: UUID, request: Request, session_id: UUID = Query(...)) -> AnalysisResult:
    try:
        result = await request.app.state.persistence.get_report(report_id, session_id)
    except PersistenceReadError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "저장소를 잠시 조회할 수 없습니다.") from error
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "저장된 리포트를 찾을 수 없습니다.")
    return result

from uuid import uuid4

from fastapi import APIRouter, Request

from app.models.schemas import ApplicantInput, IngestResponse


router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", response_model=IngestResponse)
async def ingest(data: ApplicantInput, request: Request) -> IngestResponse:
    if data.session_id is None:
        data = data.model_copy(update={"session_id": uuid4()})
    saved = await request.app.state.persistence.save_applicant(data)
    return IngestResponse(
        session_id=data.session_id,
        persistence_status="saved" if saved else "skipped",
        data=data,
    )

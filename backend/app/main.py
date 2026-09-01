from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.api import analyze, documents, ingest, products, report
from app.core.config import get_settings
from app.services.exchange_rate_client import ExchangeRateClient
from app.services.kosis_client import KosisClient
from app.services.llm_explainer import LlmExplainer
from app.services.persistence_client import PersistenceClient


settings = get_settings()
app = FastAPI(
    title="잇다 API",
    version="0.1.0",
    description="비금융 증빙을 금융기관 검토용 근거자료로 정리하는 데모 API",
)


@app.middleware("http")
async def reject_oversized_document_request(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if request.method == "POST" and request.url.path.rstrip("/") == "/api/documents":
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                content_length = int(raw_length)
            except ValueError:
                content_length = 0
            request_limit = settings.max_upload_bytes + documents.MULTIPART_OVERHEAD_BYTES
            if content_length > request_limit:
                return JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={"detail": "요청 전체 크기가 허용 범위를 초과했습니다."},
                )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.frontend_origin.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.state.settings = settings
# ponytail: process-local cache; move to a shared cache only when multiple backend instances need the same fresh value.
app.state.kosis = KosisClient(settings)
app.state.exchange = ExchangeRateClient(settings)
app.state.llm = LlmExplainer(settings)
app.state.persistence = PersistenceClient(settings)

for router in (ingest.router, documents.router, analyze.router, report.router, products.router):
    app.include_router(router, prefix="/api")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": "itda-api", "docs": "/docs"}

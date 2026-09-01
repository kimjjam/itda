import logging
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.risk_signal import detect_risk_signal
from app.core.scoring_engine import score_evidence
from app.models.schemas import (
    AnalysisEvent,
    AnalysisResult,
    ApplicantInput,
    DataSourceStatus,
)
from app.services.product_catalog import load_matched_products


router = APIRouter(prefix="/analyze", tags=["analyze"])
logger = logging.getLogger(__name__)


@router.post("/stream")
async def analyze_stream(data: ApplicantInput, request: Request) -> StreamingResponse:
    async def events():
        try:
            yield _event("kosis", "running", "통계청 배경지표를 조회하고 있습니다.")
            kosis = await request.app.state.kosis.get_population_context()
            yield _event(
                "kosis",
                "fallback" if kosis.status == DataSourceStatus.FALLBACK else "complete",
                "통계청 지표 조회를 마쳤습니다.",
                kosis.model_dump(mode="json"),
            )

            yield _event("exchange", "running", "한국수출입은행 환율을 대조하고 있습니다.")
            exchange = await request.app.state.exchange.get_rate(data.remittance_currency)
            if exchange.value is not None:
                converted = data.remittance_monthly_amount * float(exchange.value)
                note = f"{exchange.note or ''} 입력한 월 송금액은 약 {converted:,.0f}원으로 환산됩니다.".strip()
                exchange = exchange.model_copy(update={"note": note})
            yield _event(
                "exchange",
                "fallback" if exchange.status == DataSourceStatus.FALLBACK else "complete",
                "환율 대조를 마쳤습니다.",
                exchange.model_dump(mode="json"),
            )

            yield _event("scoring", "running", "제출한 근거를 일관된 규칙으로 확인하고 있습니다.")
            verified_categories = await request.app.state.persistence.get_document_categories(data.session_id)
            scoring_input = data.model_copy(update={"document_categories": verified_categories})
            scoring = score_evidence(scoring_input)
            risk_alert = detect_risk_signal(data.self_reported_risk, data.language)
            yield _event(
                "scoring",
                "complete",
                "근거 항목별 확인을 마쳤습니다.",
                {"evidence_strength": scoring.strength, "evidence_level": scoring.level},
            )

            yield _event("explanation", "running", "확인된 사실을 바탕으로 설명을 정리하고 있습니다.")
            explanation = await request.app.state.llm.explain(scoring_input, scoring, [kosis, exchange])
            summary, items = explanation
            yield _event(
                "explanation",
                "complete" if explanation.llm_succeeded else "fallback",
                "근거 설명을 정리했습니다.",
            )

            intended_status = (
                "saved"
                if request.app.state.settings.database_configured and data.session_id is not None
                else "skipped"
            )
            matched_products = await load_matched_products(
                request.app.state.persistence,
                data.visa_type,
                data.language,
            )
            result = AnalysisResult(
                report_id=uuid4(),
                evidence_strength=scoring.strength,
                evidence_level=scoring.level,
                summary=summary,
                items=items,
                risk_alert=risk_alert,
                external_metrics=[kosis, exchange],
                matched_products=matched_products,
                persistence_status=intended_status,
            )
            if intended_status == "saved" and not await request.app.state.persistence.save_report(data.session_id, result):
                result = result.model_copy(update={"persistence_status": "skipped"})
            yield _event("complete", "complete", "근거자료 리포트가 준비되었습니다.", result)
        except Exception as error:
            logger.error("Analysis stream failed: %s", type(error).__name__)
            yield _event("error", "failed", "분석을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    return StreamingResponse(events(), media_type="application/x-ndjson")


def _event(step: str, status: str, message: str, data: object = None) -> str:
    return AnalysisEvent(step=step, status=status, message=message, data=data).model_dump_json() + "\n"

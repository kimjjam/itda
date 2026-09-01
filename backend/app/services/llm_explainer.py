import base64
from collections.abc import Iterator
from dataclasses import dataclass
from io import BytesIO
import json
import math
import re
from typing import Any

import httpx
import pymupdf
from PIL import Image, UnidentifiedImageError
from pydantic import TypeAdapter, ValidationError

from app.core.config import Settings
from app.core.scoring_engine import ScoringResult
from app.models.schemas import (
    ApplicantInput,
    CurrencyCode,
    DocumentExtraction,
    EvidenceCategory,
    EvidenceItem,
    ExternalMetric,
    MonthCount,
    MonthlyIncomeKrw,
    RemittanceAmount,
)


FIELD_ALLOWLIST: dict[EvidenceCategory, set[str]] = {
    EvidenceCategory.EMPLOYMENT: {"employment_months", "monthly_income_krw"},
    EvidenceCategory.TELECOM: {"telecom_paid_months"},
    EvidenceCategory.INSURANCE: {"insurance_paid_months"},
    EvidenceCategory.REMITTANCE: {"remittance_monthly_amount", "remittance_currency", "remittance_months"},
}

FIELD_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "employment_months": TypeAdapter(MonthCount),
    "monthly_income_krw": TypeAdapter(MonthlyIncomeKrw),
    "telecom_paid_months": TypeAdapter(MonthCount),
    "insurance_paid_months": TypeAdapter(MonthCount),
    "remittance_monthly_amount": TypeAdapter(RemittanceAmount),
    "remittance_currency": TypeAdapter(CurrencyCode),
    "remittance_months": TypeAdapter(MonthCount),
}

MAX_IMAGE_PIXELS = 16_000_000
MAX_PDF_PAGES = 20
MAX_PDF_PAGES_TO_PROCESS = 3
MAX_PDF_RENDERED_PIXELS = 24_000_000
PDF_RENDER_SCALE = 1.5

FORBIDDEN_CLAIM_PATTERN = re.compile(
    r"승인|보장|심사\s*(?:결과|판정|통과|확정)|대출.{0,8}(?:가능|확정)|"
    r"확정.{0,8}(?:금리|이율)|(?:금리|이율).{0,8}확정|"
    r"\b(?:approved?|approval|guaranteed?|fixed\s+(?:interest\s+)?rate|certain\s+approval)\b|"
    r"phê\s+duyệt|được\s+duyệt|bảo\s+đảm|chắc\s+chắn|"
    r"lãi\s+suất.{0,8}(?:cố\s+định|xác\s+định)|thẩm\s+định.{0,8}(?:đạt|qua|xong)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExplanationResult:
    summary: str
    items: list[EvidenceItem]
    llm_succeeded: bool

    def __iter__(self) -> Iterator[str | list[EvidenceItem]]:
        """Keep existing two-value unpacking while exposing the LLM outcome."""
        yield self.summary
        yield self.items


class LlmExplainer:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    async def explain(
        self,
        applicant: ApplicantInput,
        scoring: ScoringResult,
        metrics: list[ExternalMetric],
    ) -> ExplanationResult:
        fallback_summary = _fallback_summary(applicant.language, scoring.level)
        if not self.settings.llm_configured:
            return ExplanationResult(fallback_summary, scoring.items, llm_succeeded=False)

        facts = {
            "evidence_level": scoring.level,
            "evidence_strength": scoring.strength,
            "visa_type": applicant.visa_type,
            "items": [item.model_dump() for item in scoring.items],
            "external_metrics": [metric.model_dump() for metric in metrics],
        }
        if applicant.language == "vi":
            prompt = (
                "Chỉ dùng các dữ kiện trong JSON sau để viết phần giải thích bằng tiếng Việt. "
                "Không dùng chữ số trong văn bản tự do và không khẳng định phê duyệt, lãi suất hay kết quả thẩm định. "
                "Trả về một đối tượng JSON gồm chuỗi summary và đối tượng explanations, mỗi item key một câu.\n"
                + json.dumps(facts, ensure_ascii=False)
            )
            system_message = "Bạn là biên tập viên tiếng Việt, chỉ diễn đạt lại các dữ kiện đã cung cấp."
        else:
            prompt = (
                "다음 JSON에 있는 사실만 사용해 금융기관 검토용 근거 설명을 작성하세요. "
                "자유 문구에 숫자를 쓰거나 승인·확정 금리·심사 결과를 단정하지 마세요. "
                "JSON 객체로 summary 문자열과 explanations 객체(item key별 한 문장)를 반환하세요.\n"
                + json.dumps(facts, ensure_ascii=False)
            )
            system_message = "당신은 입력 사실만 재서술하는 한국어 금융 근거자료 편집기입니다."
        try:
            payload = await self._chat(
                [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
            parsed = _parse_json(payload)
            summary = str(parsed.get("summary") or "").strip()
            explanations = parsed.get("explanations")
            if not summary or not isinstance(explanations, dict) or not _explanation_is_safe(summary, explanations):
                raise ValueError("unsafe explanation")
            items = [
                item.model_copy(update={"explanation": str(explanations.get(item.key) or item.explanation)})
                for item in scoring.items
            ]
            return ExplanationResult(summary, items, llm_succeeded=True)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ExplanationResult(fallback_summary, scoring.items, llm_succeeded=False)

    async def extract_document(
        self,
        category: EvidenceCategory,
        content: bytes,
        content_type: str,
    ) -> DocumentExtraction:
        try:
            images, warnings = _document_images(content, content_type)
        except (ValueError, pymupdf.FileDataError, UnidentifiedImageError, Image.DecompressionBombError):
            return DocumentExtraction(category=category, status="failed", fields={}, warnings=["지원되지 않거나 손상된 파일입니다."])
        if not self.settings.llm_configured:
            return DocumentExtraction(
                category=category,
                status="needs_review",
                fields={},
                warnings=warnings + ["문서 인식 API가 설정되지 않아 직접 입력이 필요합니다."],
            )

        allowed = sorted(FIELD_ALLOWLIST[category])
        content_parts: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"이 문서에서 {allowed} 필드만 추출하세요. 보이지 않는 값은 null로 두고 추론하지 마세요. "
                    "필드명과 값만 있는 JSON 객체로 응답하세요."
                ),
            }
        ]
        content_parts.extend(
            {"type": "image_url", "image_url": {"url": image_data_url}}
            for image_data_url in images
        )
        try:
            payload = await self._chat(
                [
                    {"role": "system", "content": "당신은 증빙 문서에서 허용된 필드만 옮겨 적는 추출기입니다."},
                    {"role": "user", "content": content_parts},
                ],
                temperature=0,
            )
            parsed = _parse_json(payload)
            fields, invalid_fields = _validated_extracted_fields(category, parsed)
            if invalid_fields:
                warnings.append("입력 범위를 벗어나 직접 확인이 필요한 필드: " + ", ".join(invalid_fields))
            status = (
                "extracted"
                if not invalid_fields and any(value is not None for value in fields.values())
                else "needs_review"
            )
            return DocumentExtraction(category=category, status=status, fields=fields, warnings=warnings)
        except (httpx.HTTPError, TypeError, ValueError, json.JSONDecodeError):
            return DocumentExtraction(
                category=category,
                status="needs_review",
                fields={},
                warnings=warnings + ["자동 추출에 실패해 직접 확인이 필요합니다."],
            )

    async def _chat(self, messages: list[dict[str, Any]], temperature: float) -> str:
        url = f"{self.settings.llm_api_base_url}/chat/completions"
        async with httpx.AsyncClient(
            timeout=max(30.0, self.settings.request_timeout_seconds),
            transport=self.transport,
        ) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
                json={"model": self.settings.llm_model, "messages": messages, "temperature": temperature},
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"])


def _document_images(content: bytes, content_type: str) -> tuple[list[str], list[str]]:
    if content_type == "application/pdf":
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise ValueError("password protected pdf")
            if document.page_count > MAX_PDF_PAGES:
                raise ValueError("pdf page limit exceeded")
            warnings = (
                [f"처음 {MAX_PDF_PAGES_TO_PROCESS}페이지만 인식했습니다."]
                if document.page_count > MAX_PDF_PAGES_TO_PROCESS
                else []
            )
            images = []
            rendered_pixels = 0
            matrix = pymupdf.Matrix(PDF_RENDER_SCALE, PDF_RENDER_SCALE)
            for page in document.pages(0, min(MAX_PDF_PAGES_TO_PROCESS, document.page_count)):
                page_pixels = math.ceil(page.rect.width * PDF_RENDER_SCALE) * math.ceil(
                    page.rect.height * PDF_RENDER_SCALE
                )
                rendered_pixels += page_pixels
                if page_pixels > MAX_IMAGE_PIXELS or rendered_pixels > MAX_PDF_RENDERED_PIXELS:
                    raise ValueError("pdf render limit exceeded")
                png = page.get_pixmap(matrix=matrix, alpha=False).tobytes("png")
                images.append(_data_url(png, "image/png"))
            if not images:
                raise ValueError("empty pdf")
            return images, warnings

    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("unsupported content type")
    with Image.open(BytesIO(content)) as image:
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError("image pixel limit exceeded")
        image.verify()
    return [_data_url(content, content_type)], []


def _validated_extracted_fields(
    category: EvidenceCategory,
    parsed: dict[str, Any],
) -> tuple[dict[str, str | int | float | None], list[str]]:
    fields: dict[str, str | int | float | None] = {}
    invalid_fields: list[str] = []
    for key in sorted(FIELD_ALLOWLIST[category]):
        if key not in parsed:
            continue
        value = parsed[key]
        if value is None:
            fields[key] = None
            continue
        if isinstance(value, bool):
            invalid_fields.append(key)
            continue
        if isinstance(value, str):
            if key == "remittance_currency":
                value = value.strip().upper()
            else:
                value = re.sub(r"[\s,]", "", value)
                if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)", value):
                    invalid_fields.append(key)
                    continue
        try:
            fields[key] = FIELD_ADAPTERS[key].validate_python(value)
        except ValidationError:
            invalid_fields.append(key)
    return fields, invalid_fields


def _data_url(content: bytes, content_type: str) -> str:
    return f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}"


def _parse_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("expected object")
    return parsed


def _fallback_summary(language: str, level: str) -> str:
    if language == "vi":
        localized_level = {
            "충분": "đầy đủ",
            "보통": "trung bình",
            "추가 자료 필요": "cần bổ sung tài liệu",
        }.get(level, level)
        return (
            f"Mức độ đầy đủ của hồ sơ đã nộp là '{localized_level}'. "
            "Vui lòng xem xét căn cứ của từng mục."
        )
    return f"제출된 자료의 근거 충족도는 '{level}' 단계입니다. 각 항목의 확인 근거를 함께 검토해 주세요."


def _explanation_is_safe(summary: str, explanations: dict[object, object]) -> bool:
    texts = [summary]
    for value in explanations.values():
        if not isinstance(value, str):
            return False
        texts.append(value)
    return all(not re.search(r"\d", text) and not FORBIDDEN_CLAIM_PATTERN.search(text) for text in texts)

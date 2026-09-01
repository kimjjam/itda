from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class EvidenceCategory(str, Enum):
    EMPLOYMENT = "employment"
    TELECOM = "telecom"
    INSURANCE = "insurance"
    REMITTANCE = "remittance"


class DataSourceStatus(str, Enum):
    LIVE = "live"
    CACHE = "cache"
    FALLBACK = "fallback"


VisaType = Literal["E-9", "E-7", "F-2", "F-6", "D-2"]
Language = Literal["ko", "vi"]
MonthCount = Annotated[int, Field(ge=0, le=600)]
MonthlyIncomeKrw = Annotated[int, Field(ge=0, le=100_000_000)]
RemittanceAmount = Annotated[float, Field(ge=0, le=1_000_000_000)]
CurrencyCode = Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")]


class ApplicantInput(BaseModel):
    session_id: UUID | None = None
    language: Language = "ko"
    nationality: str = Field(min_length=2, max_length=40)
    visa_type: VisaType
    employment_months: MonthCount
    monthly_income_krw: MonthlyIncomeKrw
    telecom_paid_months: MonthCount
    insurance_paid_months: MonthCount
    remittance_monthly_amount: RemittanceAmount
    remittance_currency: CurrencyCode
    remittance_months: MonthCount
    document_categories: list[EvidenceCategory] = Field(default_factory=list)
    self_reported_risk: bool = False

    @field_validator("nationality")
    @classmethod
    def normalize_nationality(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("remittance_currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class ExternalMetric(BaseModel):
    name: str
    value: float | str | None = None
    unit: str | None = None
    status: DataSourceStatus
    source_name: str
    checked_at: str
    note: str | None = None


class EvidenceItem(BaseModel):
    key: str
    title: str
    value: str
    strength: Literal["strong", "moderate", "limited"]
    explanation: str
    source: str


class RiskAlert(BaseModel):
    active: bool
    message: str | None = None
    guidance: str | None = None


class Product(BaseModel):
    name: str
    provider: str
    category: Literal[
        "저축은행_신용대출",
        "시중은행_전세대출",
        "시중은행_외국인신용대출",
    ]
    eligible_visas: list[str] = Field(default_factory=list)
    limit_text: str | None = None
    rate_text: str | None = None
    requirement_text: str | None = None
    source_url: str | None = None
    verified_at: str | None = None
    match_reason: str


class AnalysisResult(BaseModel):
    report_id: UUID
    evidence_strength: int = Field(ge=0, le=100)
    evidence_level: Literal["충분", "보통", "추가 자료 필요"]
    summary: str
    items: list[EvidenceItem]
    risk_alert: RiskAlert
    external_metrics: list[ExternalMetric]
    matched_products: list[Product]
    persistence_status: Literal["saved", "skipped"] = "skipped"


class AnalysisEvent(BaseModel):
    step: Literal["kosis", "exchange", "scoring", "explanation", "complete", "error"]
    status: Literal["running", "complete", "fallback", "failed"]
    message: str
    data: dict[str, Any] | AnalysisResult | None = None


class DocumentExtraction(BaseModel):
    category: EvidenceCategory
    status: Literal["extracted", "needs_review", "failed"]
    fields: dict[str, str | int | float | None]
    warnings: list[str] = Field(default_factory=list)
    upload_id: UUID | None = None


class IngestResponse(BaseModel):
    session_id: UUID
    persistence_status: Literal["saved", "skipped"]
    data: ApplicantInput

import type {
  AnalysisEvent,
  AnalysisResult,
  ApplicantInput,
  DocumentExtraction,
  EvidenceCategory,
} from "../types";
import i18n from "../i18n";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function ingestApplicant(data: ApplicantInput): Promise<ApplicantInput> {
  const response = await fetch(`${API_BASE_URL}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const payload: unknown = await response.json();
  if (!response.ok || !isRecord(payload) || !isApplicantInput(payload.data)) {
    throw new ApiError(i18n.t("errors.ingest"));
  }
  return { ...payload.data, language: data.language };
}

export async function extractDocument(
  sessionId: string,
  category: EvidenceCategory,
  file: File,
): Promise<DocumentExtraction> {
  const form = new FormData();
  form.set("session_id", sessionId);
  form.set("category", category);
  form.set("file", file);
  const response = await fetch(`${API_BASE_URL}/documents`, { method: "POST", body: form });
  const payload: unknown = await response.json();
  if (!response.ok || !isDocumentExtraction(payload)) {
    throw new ApiError(i18n.t("errors.document"));
  }
  return payload;
}

export async function streamAnalysis(
  data: ApplicantInput,
  onEvent: (event: AnalysisEvent) => void,
  signal?: AbortSignal,
): Promise<AnalysisResult> {
  const response = await fetch(`${API_BASE_URL}/analyze/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new ApiError(i18n.t("errors.analysisStart"));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: AnalysisResult | null = null;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const parsed: unknown = JSON.parse(line);
      if (!isAnalysisEvent(parsed)) continue;
      onEvent(parsed);
      if (parsed.step === "error") throw new ApiError(i18n.t("errors.analysisFailed"));
      if (parsed.step === "complete" && isAnalysisResult(parsed.data)) result = parsed.data;
    }
    if (done) break;
  }
  if (!result) throw new ApiError(i18n.t("errors.reportMissing"));
  return result;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isDocumentExtraction(value: unknown): value is DocumentExtraction {
  return isRecord(value)
    && isOneOf(value.category, ["employment", "telecom", "insurance", "remittance"])
    && isOneOf(value.status, ["extracted", "needs_review", "failed"])
    && isRecord(value.fields)
    && Object.values(value.fields).every(isExtractionValue)
    && Array.isArray(value.warnings)
    && value.warnings.every((warning) => typeof warning === "string")
    && (value.upload_id === null || typeof value.upload_id === "string");
}

function isAnalysisEvent(value: unknown): value is AnalysisEvent {
  return isRecord(value)
    && isOneOf(value.step, ["kosis", "exchange", "scoring", "explanation", "complete", "error"])
    && isOneOf(value.status, ["running", "complete", "fallback", "failed"])
    && typeof value.message === "string";
}

function isAnalysisResult(value: unknown): value is AnalysisResult {
  return isRecord(value)
    && typeof value.report_id === "string"
    && isBoundedNumber(value.evidence_strength, 0, 100)
    && isOneOf(value.evidence_level, ["충분", "보통", "추가 자료 필요"])
    && typeof value.summary === "string"
    && Array.isArray(value.items)
    && value.items.every(isEvidenceItem)
    && isRiskAlert(value.risk_alert)
    && Array.isArray(value.external_metrics)
    && value.external_metrics.every(isExternalMetric)
    && Array.isArray(value.matched_products)
    && value.matched_products.every(isProduct)
    && isOneOf(value.persistence_status, ["saved", "skipped"]);
}

function isApplicantInput(value: unknown): value is Omit<ApplicantInput, "language"> & { language?: ApplicantInput["language"] } {
  return isRecord(value)
    && typeof value.session_id === "string"
    && (value.language === undefined || isOneOf(value.language, ["ko", "vi"]))
    && typeof value.nationality === "string"
    && isOneOf(value.visa_type, ["E-9", "E-7", "F-2", "F-6", "D-2"])
    && isBoundedInteger(value.employment_months, 0, 600)
    && isBoundedInteger(value.monthly_income_krw, 0, 100_000_000)
    && isBoundedInteger(value.telecom_paid_months, 0, 600)
    && isBoundedInteger(value.insurance_paid_months, 0, 600)
    && isBoundedNumber(value.remittance_monthly_amount, 0, 1_000_000_000)
    && isOneOf(value.remittance_currency, ["VND", "USD", "PHP", "IDR", "NPR", "KHR", "MMK", "KRW"])
    && isBoundedInteger(value.remittance_months, 0, 600)
    && Array.isArray(value.document_categories)
    && value.document_categories.every((category) => isOneOf(category, ["employment", "telecom", "insurance", "remittance"]))
    && typeof value.self_reported_risk === "boolean";
}

function isEvidenceItem(value: unknown): boolean {
  return isRecord(value)
    && typeof value.key === "string"
    && typeof value.title === "string"
    && typeof value.value === "string"
    && isOneOf(value.strength, ["strong", "moderate", "limited"])
    && typeof value.explanation === "string"
    && typeof value.source === "string";
}

function isRiskAlert(value: unknown): boolean {
  return isRecord(value)
    && typeof value.active === "boolean"
    && isNullableString(value.message)
    && isNullableString(value.guidance);
}

function isExternalMetric(value: unknown): boolean {
  return isRecord(value)
    && typeof value.name === "string"
    && (value.value === null || typeof value.value === "string" || (typeof value.value === "number" && Number.isFinite(value.value)))
    && isNullableString(value.unit)
    && isOneOf(value.status, ["live", "cache", "fallback"])
    && typeof value.source_name === "string"
    && typeof value.checked_at === "string"
    && isNullableString(value.note);
}

function isProduct(value: unknown): boolean {
  return isRecord(value)
    && typeof value.name === "string"
    && typeof value.provider === "string"
    && isOneOf(value.category, ["저축은행_신용대출", "시중은행_전세대출", "시중은행_외국인신용대출"])
    && Array.isArray(value.eligible_visas)
    && value.eligible_visas.every((visa) => typeof visa === "string")
    && isNullableString(value.limit_text)
    && isNullableString(value.rate_text)
    && isNullableString(value.requirement_text)
    && isNullableString(value.source_url)
    && isNullableString(value.verified_at)
    && typeof value.match_reason === "string";
}

function isOneOf<const T extends readonly string[]>(value: unknown, allowed: T): value is T[number] {
  return typeof value === "string" && allowed.includes(value);
}

function isNullableString(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function isBoundedNumber(value: unknown, min: number, max: number): boolean {
  return typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
}

function isBoundedInteger(value: unknown, min: number, max: number): boolean {
  return isBoundedNumber(value, min, max) && Number.isInteger(value);
}

function isExtractionValue(value: unknown): boolean {
  return value === null || typeof value === "string" || (typeof value === "number" && Number.isFinite(value));
}

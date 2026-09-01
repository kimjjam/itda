export type AppStage = "landing" | "collect" | "analysis" | "report";
export type EvidenceCategory = "employment" | "telecom" | "insurance" | "remittance";
export type VisaType = "E-9" | "E-7" | "F-2" | "F-6" | "D-2";
export type AppLanguage = "ko" | "vi";

export interface ApplicantInput {
  session_id: string;
  language: AppLanguage;
  nationality: string;
  visa_type: VisaType;
  employment_months: number;
  monthly_income_krw: number;
  telecom_paid_months: number;
  insurance_paid_months: number;
  remittance_monthly_amount: number;
  remittance_currency: string;
  remittance_months: number;
  document_categories: EvidenceCategory[];
  self_reported_risk: boolean;
}

export interface DocumentExtraction {
  category: EvidenceCategory;
  status: "extracted" | "needs_review" | "failed";
  fields: Record<string, string | number | null>;
  warnings: string[];
  upload_id: string | null;
}

export interface ExternalMetric {
  name: string;
  value: number | string | null;
  unit: string | null;
  status: "live" | "cache" | "fallback";
  source_name: string;
  checked_at: string;
  note: string | null;
}

export interface EvidenceItem {
  key: string;
  title: string;
  value: string;
  strength: "strong" | "moderate" | "limited";
  explanation: string;
  source: string;
}

export interface RiskAlert {
  active: boolean;
  message: string | null;
  guidance: string | null;
}

export interface Product {
  name: string;
  provider: string;
  category: "저축은행_신용대출" | "시중은행_전세대출" | "시중은행_외국인신용대출";
  eligible_visas: string[];
  limit_text: string | null;
  rate_text: string | null;
  requirement_text: string | null;
  source_url: string | null;
  verified_at: string | null;
  match_reason: string;
}

export interface AnalysisResult {
  report_id: string;
  evidence_strength: number;
  evidence_level: "충분" | "보통" | "추가 자료 필요";
  summary: string;
  items: EvidenceItem[];
  risk_alert: RiskAlert;
  external_metrics: ExternalMetric[];
  matched_products: Product[];
  persistence_status: "saved" | "skipped";
}

export interface AnalysisEvent {
  step: "kosis" | "exchange" | "scoring" | "explanation" | "complete" | "error";
  status: "running" | "complete" | "fallback" | "failed";
  message: string;
  data: unknown;
}

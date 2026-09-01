import { ArrowLeft, ArrowRight, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import EvidenceUpload from "../components/EvidenceUpload";
import { ApiError } from "../lib/api";
import type { ApplicantInput, EvidenceCategory } from "../types";


interface Props {
  initialData: ApplicantInput;
  onComplete: (data: ApplicantInput) => Promise<void>;
}

const STEP_KEYS = ["profile", "employment", "payments", "remittance", "risk"] as const;
const CURRENCIES = ["VND", "USD", "PHP", "IDR", "NPR", "KHR", "MMK", "KRW"] as const;
const NUMERIC_FIELDS = {
  employment_months: { max: 600, integer: true },
  monthly_income_krw: { max: 100_000_000, integer: true },
  telecom_paid_months: { max: 600, integer: true },
  insurance_paid_months: { max: 600, integer: true },
  remittance_monthly_amount: { max: 1_000_000_000, integer: false },
  remittance_months: { max: 600, integer: true },
} as const;

type NumericField = keyof typeof NUMERIC_FIELDS;

function parseExtractedNumber(value: string | number | null | undefined, field: NumericField): number | null {
  let parsed: number;
  if (typeof value === "number") {
    parsed = value;
  } else if (typeof value === "string") {
    const normalized = value.trim().replace(/[\s,]/g, "");
    const match = normalized.match(/^(?:약|월평균|평균|월|about|avg\.?)?(?:₩|₫|\$|KRW|VND|USD|PHP|IDR|NPR|KHR|MMK)?(\d+(?:\.\d+)?)(?:개월|달|months?|tháng|원|KRW|VND|USD|PHP|IDR|NPR|KHR|MMK)?$/iu);
    if (!match) return null;
    parsed = Number(match[1]);
  } else {
    return null;
  }

  const { max, integer } = NUMERIC_FIELDS[field];
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > max || (integer && !Number.isInteger(parsed))) return null;
  return parsed;
}

function isCurrency(value: string): value is (typeof CURRENCIES)[number] {
  return CURRENCIES.includes(value as (typeof CURRENCIES)[number]);
}

export default function InfoCollect({ initialData, onComplete }: Props) {
  const { t } = useTranslation();
  const [data, setData] = useState(initialData);
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const isLast = step === STEP_KEYS.length - 1;

  const setNumber = (key: keyof ApplicantInput, value: string) => {
    setData((current) => ({ ...current, [key]: Math.max(0, Number(value) || 0) }));
  };

  const applyExtraction = (category: EvidenceCategory, fields: Record<string, string | number | null>): boolean => {
    const numericUpdates: Partial<Record<NumericField, number>> = {};
    for (const key of Object.keys(NUMERIC_FIELDS) as NumericField[]) {
      const parsed = parseExtractedNumber(fields[key], key);
      if (parsed !== null) numericUpdates[key] = parsed;
    }

    const currency = typeof fields.remittance_currency === "string" ? fields.remittance_currency.trim().toUpperCase() : "";
    const hasCurrency = isCurrency(currency);
    if (Object.keys(numericUpdates).length === 0 && !hasCurrency) return false;

    setData((current) => {
      const next = { ...current, ...numericUpdates };
      return {
        ...next,
        remittance_currency: hasCurrency ? currency : next.remittance_currency,
        document_categories: Array.from(new Set([...next.document_categories, category])),
      };
    });
    return true;
  };

  const submit = async () => {
    setSubmitting(true);
    setError("");
    try {
      await onComplete(data);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : t("errors.form"));
      setSubmitting(false);
    }
  };

  return (
    <main className="flow-main collect-layout">
      <aside className="flow-sidebar">
        <p className="simulation-label"><ShieldCheck size={15} /> {t("common.simulation")}</p>
        <h1>{t("collect.title")}</h1>
        <p>{t("collect.description")}</p>
        <ol className="wizard-steps">
          {STEP_KEYS.map((key, index) => (
            <li key={key} className={index === step ? "active" : index < step ? "done" : ""}>
              <span>{index + 1}</span>{t(`collect.steps.${key}`)}
            </li>
          ))}
        </ol>
      </aside>

      <section className="form-card" aria-labelledby="step-title">
        <div className="mobile-progress">
          <span>{t("collect.progress", { current: step + 1, total: STEP_KEYS.length })}</span>
          <i style={{ width: `${((step + 1) / STEP_KEYS.length) * 100}%` }} />
        </div>
        <form onSubmit={(event) => { event.preventDefault(); isLast ? void submit() : setStep((current) => current + 1); }}>
          {step === 0 && (
            <fieldset>
              <legend id="step-title">{t("collect.profileQuestion")}</legend>
              <label>{t("collect.nationality")}<input required value={data.nationality} placeholder={t("collect.nationalityPlaceholder")} onChange={(event) => setData({ ...data, nationality: event.target.value })} /></label>
              <label>{t("collect.visa")}<select value={data.visa_type} onChange={(event) => setData({ ...data, visa_type: event.target.value as ApplicantInput["visa_type"] })}>{["E-9", "E-7", "F-2", "F-6", "D-2"].map((visa) => <option key={visa}>{visa}</option>)}</select></label>
            </fieldset>
          )}
          {step === 1 && (
            <fieldset>
              <legend id="step-title">{t("collect.employmentQuestion")}</legend>
              <label>{t("collect.employmentMonths")}<input type="number" min="0" max="600" required value={data.employment_months} onChange={(event) => setNumber("employment_months", event.target.value)} /></label>
              <label>{t("collect.monthlyIncome")}<input type="number" min="0" max="100000000" step="10000" required value={data.monthly_income_krw} onChange={(event) => setNumber("monthly_income_krw", event.target.value)} /></label>
              <EvidenceUpload category="employment" sessionId={data.session_id} onExtracted={applyExtraction} />
            </fieldset>
          )}
          {step === 2 && (
            <fieldset>
              <legend id="step-title">{t("collect.paymentsQuestion")}</legend>
              <label>{t("collect.telecomMonths")}<input type="number" min="0" max="600" required value={data.telecom_paid_months} onChange={(event) => setNumber("telecom_paid_months", event.target.value)} /></label>
              <EvidenceUpload category="telecom" sessionId={data.session_id} onExtracted={applyExtraction} />
              <label>{t("collect.insuranceMonths")}<input type="number" min="0" max="600" required value={data.insurance_paid_months} onChange={(event) => setNumber("insurance_paid_months", event.target.value)} /></label>
              <EvidenceUpload category="insurance" sessionId={data.session_id} onExtracted={applyExtraction} />
            </fieldset>
          )}
          {step === 3 && (
            <fieldset>
              <legend id="step-title">{t("collect.remittanceQuestion")}</legend>
              <div className="split-fields">
                <label>{t("collect.remittanceAmount")}<input type="number" min="0" required value={data.remittance_monthly_amount} onChange={(event) => setNumber("remittance_monthly_amount", event.target.value)} /></label>
                <label>{t("collect.currency")}<select value={data.remittance_currency} onChange={(event) => setData({ ...data, remittance_currency: event.target.value })}>{CURRENCIES.map((currency) => <option key={currency}>{currency}</option>)}</select></label>
              </div>
              <label>{t("collect.remittanceMonths")}<input type="number" min="0" max="600" required value={data.remittance_months} onChange={(event) => setNumber("remittance_months", event.target.value)} /></label>
              <EvidenceUpload category="remittance" sessionId={data.session_id} onExtracted={applyExtraction} />
            </fieldset>
          )}
          {step === 4 && (
            <fieldset>
              <legend id="step-title">{t("collect.riskQuestion")}</legend>
              <label className="checkbox-field"><input type="checkbox" checked={data.self_reported_risk} onChange={(event) => setData({ ...data, self_reported_risk: event.target.checked })} /><span><strong>{t("collect.riskLabel")}</strong><small>{t("collect.riskHelp")}</small></span></label>
              <div className="review-summary"><span>{data.nationality} · {data.visa_type}</span><span>{t("collect.reviewEmployment", { months: data.employment_months })}</span><span>{t("collect.reviewEvidence", { count: data.document_categories.length })}</span></div>
            </fieldset>
          )}

          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="form-actions">
            <button className="secondary-action" type="button" disabled={step === 0 || submitting} onClick={() => setStep((current) => current - 1)}><ArrowLeft size={18} /> {t("common.back")}</button>
            <button className="primary-action" type="submit" disabled={submitting}>{submitting ? t("common.loading") : isLast ? t("collect.submit") : t("common.next")} {!submitting && <ArrowRight size={18} />}</button>
          </div>
        </form>
      </section>
    </main>
  );
}

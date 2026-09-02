import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import LanguageToggle from "./components/LanguageToggle";
import { ingestApplicant } from "./lib/api";
import AIAnalysis from "./pages/AIAnalysis";
import InfoCollect from "./pages/InfoCollect";
import Landing from "./pages/Landing";
import ReportResult from "./pages/ReportResult";
import type { AnalysisResult, ApplicantInput, AppLanguage, AppStage } from "./types";


function newApplicant(language: AppLanguage): ApplicantInput {
  return {
    session_id: crypto.randomUUID(),
    language,
    nationality: "",
    visa_type: "E-9",
    employment_months: 0,
    monthly_income_krw: 0,
    telecom_paid_months: 0,
    insurance_paid_months: 0,
    remittance_monthly_amount: 0,
    remittance_currency: "VND",
    remittance_months: 0,
    document_categories: [],
    self_reported_risk: false,
  };
}

export default function App() {
  const { i18n, t } = useTranslation();
  const language: AppLanguage = i18n.resolvedLanguage === "vi" ? "vi" : "ko";
  const [stage, setStage] = useState<AppStage>("landing");
  const [applicant, setApplicant] = useState<ApplicantInput>(() => newApplicant(language));
  const [result, setResult] = useState<AnalysisResult | null>(null);

  const completeCollection = async (data: ApplicantInput) => {
    const saved = await ingestApplicant({ ...data, language });
    setApplicant(saved);
    setStage("analysis");
  };

  const completeAnalysis = useCallback((analysis: AnalysisResult) => {
    setApplicant((current) => current.language === language
      ? current
      : { ...current, language });
    setResult(analysis);
    setStage("report");
  }, [language]);

  useEffect(() => {
    if (stage !== "report" || applicant.language === language) return;
    setApplicant((current) => current.language === language ? current : { ...current, language });
    setStage("analysis");
  }, [applicant.language, language, stage]);

  const restart = () => {
    setApplicant(newApplicant(language));
    setResult(null);
    setStage("landing");
  };

  return (
    <div className="app-shell">
      <header className="site-header">
        <button className="brand" type="button" onClick={() => setStage("landing")} aria-label={t("common.homeLabel")}>
          <span className="brand-mark" aria-hidden="true">{t("common.brandMark")}</span>
          <span>{t("common.brand")}</span>
        </button>
        <LanguageToggle />
      </header>
      {stage === "landing" && <Landing onStart={() => setStage("collect")} />}
      {stage === "collect" && <InfoCollect initialData={applicant} onComplete={completeCollection} />}
      {stage === "analysis" && <AIAnalysis data={applicant} onComplete={completeAnalysis} />}
      {stage === "report" && result && <ReportResult result={result} onRestart={restart} />}
    </div>
  );
}

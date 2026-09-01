import { AlertTriangle, Check, Circle, Database, FileText, RefreshCw, Scale, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, streamAnalysis } from "../lib/api";
import type { AnalysisEvent, AnalysisResult, ApplicantInput } from "../types";


interface Props {
  data: ApplicantInput;
  onComplete: (result: AnalysisResult) => void;
}

const STEPS = [
  { key: "kosis", icon: Database },
  { key: "exchange", icon: Scale },
  { key: "scoring", icon: FileText },
  { key: "explanation", icon: Sparkles },
] as const;

export default function AIAnalysis({ data, onComplete }: Props) {
  const { i18n, t } = useTranslation();
  const language = i18n.resolvedLanguage === "vi" ? "vi" : "ko";
  const [events, setEvents] = useState<AnalysisEvent[]>([]);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setEvents([]);
    setError("");
    void streamAnalysis({ ...data, language }, (event) => {
      if (controller.signal.aborted) return;
      setEvents((current) => {
        const index = current.findIndex((item) => item.step === event.step);
        if (index < 0) return [...current, event];
        const next = [...current];
        next[index] = event;
        return next;
      });
    }, controller.signal).then((result) => {
      if (!controller.signal.aborted) onComplete(result);
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      setError(reason instanceof ApiError ? reason.message : t("errors.analysisFailed"));
    });
    return () => controller.abort();
  }, [attempt, data, language, onComplete, t]);

  const retry = () => {
    setAttempt((current) => current + 1);
  };

  const latestEvent = events.at(-1);
  const latestStep = STEPS.find(({ key }) => key === latestEvent?.step);
  const latestStatus = latestEvent?.status === "running"
    ? t("common.loading")
    : latestEvent?.status === "fallback"
      ? t("analysis.fallback")
      : latestEvent?.status === "complete"
        ? t("analysis.complete")
        : t("analysis.waiting");
  const announcement = latestStep
    ? `${t(`analysis.steps.${latestStep.key}`)}: ${latestStatus}`
    : latestEvent?.step === "complete"
      ? t("analysis.reportReady")
      : "";
  const isBusy = !error && latestEvent?.step !== "complete";

  return (
    <main className="flow-main analysis-layout">
      <section className="analysis-copy">
        <span className="agent-orbit" aria-hidden="true"><Sparkles size={28} /></span>
        <h1>{t("analysis.title")}</h1>
        <p>{t("analysis.description")}</p>
      </section>

      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{announcement}</p>
      <section className="analysis-card" aria-busy={isBusy}>
        <ol>
          {STEPS.map(({ key, icon: Icon }) => {
            const event = events.find((item) => item.step === key);
            const status = event?.status ?? "waiting";
            return (
              <li key={key} className={status}>
                <span className="analysis-icon"><Icon size={21} aria-hidden="true" /></span>
                <span className="analysis-step-copy">
                  <strong>{t(`analysis.steps.${key}`)}</strong>
                  <small>{status === "running" ? t("common.loading") : status === "fallback" ? t("analysis.fallback") : status === "complete" ? t("analysis.complete") : t("analysis.waiting")}</small>
                </span>
                <span className="analysis-state" aria-hidden="true">
                  {status === "running" ? <RefreshCw className="spin" size={20} /> : status === "complete" || status === "fallback" ? <Check size={20} /> : <Circle size={17} />}
                </span>
              </li>
            );
          })}
        </ol>
        {error && (
          <div className="analysis-error" role="alert">
            <AlertTriangle size={20} />
            <div><strong>{t("analysis.errorTitle")}</strong><p>{error}</p></div>
            <button type="button" onClick={retry}>{t("common.retry")}</button>
          </div>
        )}
      </section>
    </main>
  );
}

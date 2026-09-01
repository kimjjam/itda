import { ArrowRight, Database, FileSearch, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";


interface Props {
  onStart: () => void;
}

export default function Landing({ onStart }: Props) {
  const { t } = useTranslation();
  const processSteps = [
    { icon: FileSearch, title: t("landing.steps.document.0"), detail: t("landing.steps.document.1") },
    { icon: Database, title: t("landing.steps.context.0"), detail: t("landing.steps.context.1") },
    { icon: ShieldCheck, title: t("landing.steps.report.0"), detail: t("landing.steps.report.1") },
  ];

  return (
    <>
      <main className="landing-main">
        <section className="hero-copy" aria-labelledby="hero-title">
          <h1 id="hero-title">{t("landing.title1")}<br />{t("landing.title2")}</h1>
          <p>{t("landing.description")}</p>
          <button className="primary-action" type="button" onClick={onStart}>
            {t("common.start")} <ArrowRight size={19} aria-hidden="true" />
          </button>
          <p className="simulation-note">{t("common.simulation")} {t("common.finalReview")}</p>
        </section>

        <section className="agent-panel" aria-labelledby="agent-title">
          <div className="agent-panel-header">
            <div><h2 id="agent-title">{t("landing.agentTitle")}</h2><p>{t("landing.agentDescription")}</p></div>
            <span className="status-dot"><i aria-hidden="true" /> {t("landing.ready")}</span>
          </div>
          <ol className="process-list">
            {processSteps.map(({ icon: Icon, title, detail }, index) => (
              <li key={title}>
                <span className="step-number">0{index + 1}</span>
                <Icon size={21} strokeWidth={1.8} aria-hidden="true" />
                <span><strong>{title}</strong><small>{detail}</small></span>
              </li>
            ))}
          </ol>
          <div className="evidence-summary">
            <span>{t("landing.output")}</span><strong>{t("landing.outputValue")}</strong>
          </div>
        </section>
      </main>
      <footer className="trust-strip" aria-label="Service principles">
        {[0, 1, 2].map((index) => <span key={index}>{t(`landing.principles.${index}`)}</span>)}
      </footer>
    </>
  );
}


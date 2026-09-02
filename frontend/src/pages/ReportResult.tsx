import { ArrowRight, CheckCircle2, ExternalLink, FileCheck2, RotateCcw, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AnalysisResult, Product } from "../types";


interface Props {
  result: AnalysisResult;
  onRestart: () => void;
}

const strengthLabel = { strong: "strong", moderate: "moderate", limited: "limited" } as const;

function externalSourceKey(sourceName: string) {
  if (sourceName.includes("KOSIS")) return "report.externalSources.kosis";
  if (sourceName.includes("한국수출입은행") || sourceName.includes("Korea Eximbank")) return "report.externalSources.exchange";
  return null;
}

export default function ReportResult({ result, onRestart }: Props) {
  const { t } = useTranslation();
  const savings = result.matched_products.filter((product) => product.category === "저축은행_신용대출");
  const banks = result.matched_products.filter((product) => product.category !== "저축은행_신용대출");

  return (
    <main className="report-main">
      <section className="report-hero">
        <div className="report-title-row">
          <span className="report-icon"><FileCheck2 size={25} /></span>
          <div><p>{t("report.title")}</p><h1>{result.summary}</h1></div>
        </div>
        <div className="strength-panel">
          <div><span>{t("report.level")}</span><strong>{t(`report.levelValues.${result.evidence_level}`)}</strong></div>
          <b>{result.evidence_strength}<small>/100</small></b>
          <div className="strength-track" aria-label={`${result.evidence_strength}%`}><i style={{ width: `${result.evidence_strength}%` }} /></div>
          <p>{t("report.notDecision")}</p>
        </div>
      </section>

      {result.risk_alert.active && (
        <section className="risk-banner" aria-labelledby="risk-title">
          <ShieldAlert size={24} />
          <div><h2 id="risk-title">{t("report.riskTitle")}</h2><p>{t("report.riskGuidance")}</p></div>
          <a href="https://www.kinfa.or.kr/counselingSupport/centerIntroduction.do" target="_blank" rel="noreferrer">{t("report.counselingLink")} <ExternalLink size={15} /></a>
        </section>
      )}

      <section className="report-section" aria-labelledby="evidence-title">
        <div className="section-heading"><span>01</span><div><h2 id="evidence-title">{t("report.why")}</h2><p>{t("common.finalReview")}</p></div></div>
        <div className="evidence-grid">
          {result.items.map((item) => (
            <article className="evidence-card" key={item.key}>
              <div><span className={`strength-tag ${item.strength}`}>{t(`report.strength.${strengthLabel[item.strength]}`)}</span><strong>{item.value}</strong></div>
              <h3>{item.title}</h3><p>{item.explanation}</p><small><CheckCircle2 size={13} /> {item.source}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="report-section comparison-section" aria-labelledby="comparison-title">
        <div className="section-heading"><span>02</span><div><h2 id="comparison-title">{t("report.asIsTitle")}</h2></div></div>
        <div className="comparison-row"><div><small>AS-IS</small><p>{t("report.asIs")}</p></div><ArrowRight aria-hidden="true" /><div><small>ITDA</small><p>{t("report.toBe")}</p></div></div>
      </section>

      <section className="report-section" aria-labelledby="products-title">
        <div className="section-heading"><span>03</span><div><h2 id="products-title">{t("report.products")}</h2><p>{t("report.productsNote")}</p></div></div>
        <ProductGroup title={t("report.savings")} products={savings} sourceLabel={t("report.source")} conditionsLabel={t("report.conditions")} limitLabel={t("report.limit")} rateLabel={t("report.rate")} />
        <ProductGroup title={t("report.banks")} products={banks} sourceLabel={t("report.source")} conditionsLabel={t("report.conditions")} limitLabel={t("report.limit")} rateLabel={t("report.rate")} />
      </section>

      <section className="source-status" aria-label="External data status">
        {result.external_metrics.map((metric) => {
          const sourceKey = externalSourceKey(metric.source_name);
          return <span key={metric.name} className={metric.status}><i />{sourceKey ? t(sourceKey) : metric.source_name} · {t(`report.sourceStatus.${metric.status}`)}</span>;
        })}
      </section>
      <button className="restart-button" type="button" onClick={onRestart}><RotateCcw size={17} /> {t("report.newReport")}</button>
    </main>
  );
}

function ProductGroup({ title, products, sourceLabel, conditionsLabel, limitLabel, rateLabel }: { title: string; products: Product[]; sourceLabel: string; conditionsLabel: string; limitLabel: string; rateLabel: string }) {
  return (
    <div className="product-group">
      <h3>{title}<span>{products.length}</span></h3>
      <div className="product-list">
        {products.map((product) => (
          <article className="product-card" key={`${product.provider}-${product.name}`}>
            <div><small>{product.provider}</small><h4>{product.name}</h4></div>
            <p>{product.match_reason}</p>
            <dl>
              {product.limit_text && <><dt>{limitLabel}</dt><dd>{product.limit_text}</dd></>}
              {product.rate_text && <><dt>{rateLabel}</dt><dd>{product.rate_text}</dd></>}
              <dt>{conditionsLabel}</dt><dd>{product.requirement_text}</dd>
            </dl>
            {product.source_url && <a href={product.source_url} target="_blank" rel="noreferrer">{sourceLabel} <ExternalLink size={14} /></a>}
          </article>
        ))}
      </div>
    </div>
  );
}

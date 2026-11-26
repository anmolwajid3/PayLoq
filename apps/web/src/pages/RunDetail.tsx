import { Fragment, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import * as api from "../api";
import type { Run } from "../api";
import { useAuth } from "../auth";
import { ArtifactViewer } from "../components/ArtifactViewer";
import { BalanceHistoryChart, ProjectionChart } from "../components/CashChart";
import { ChatDemo } from "../components/ChatDemo";
import { SoftWarnings, ValidationPanel } from "../components/SoftWarnings";
import { fmtEur } from "../lib/format";
import { resolveFieldSummary } from "../lib/fieldSummary";
import { t } from "../i18n";

function normText(s: string | null | undefined): string {
  return (s || "").trim().replace(/\s+/g, " ");
}

function fmtScore(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(2);
}

export function RunDetailPage() {
  const { id = "" } = useParams();
  const { lang } = useAuth();
  const [run, setRun] = useState<Run | null>(null);
  const [jsonText, setJsonText] = useState<string | null>(null);
  const [jsonName, setJsonName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [expandedAnswer, setExpandedAnswer] = useState<string | null>(null);

  useEffect(() => {
    const runId = Number(id);
    if (!runId) return;
    api
      .getRun(runId)
      .then(setRun)
      .catch((e) => setError(e instanceof Error ? e.message : "Error"));
  }, [id]);

  async function viewJson(filename: string) {
    if (!run) return;
    try {
      const text = await api.fetchArtifactText(run.id, filename);
      setJsonName(filename);
      setJsonText(text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    }
  }

  async function handleExportPdf() {
    if (!run || run.status !== "ok") return;
    setPdfBusy(true);
    setError(null);
    try {
      const { exportRunPdf } = await import("../lib/exportRunPdf");
      exportRunPdf(run, lang);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setPdfBusy(false);
    }
  }

  if (!run && !error) return <p className="muted">{t("loading", lang)}</p>;

  const summary = run?.pack_summary;
  const soft = summary?.nl_soft_warnings || [];
  const params = summary?.parameters;

  const fromText = normText(run?.from_text);
  const descFi = normText(summary?.description?.fi);
  const descEn = normText(summary?.description?.en);
  // Deduplicate Input text vs Description when from_text mirrors description.
  const fromTextDupesDescription =
    Boolean(fromText) && (fromText === descFi || fromText === descEn);
  const showFromText = Boolean(fromText) && !fromTextDupesDescription;
  const showDescription = Boolean(descFi || descEn);

  const llmLabel = run
    ? run.llm_model
      ? `${run.llm_adapter} · ${run.llm_model}`
      : run.llm_adapter
    : "";

  return (
    <div className={run?.status === "ok" ? "run-layout" : undefined}>
      <div className="run-main">
        <p>
          <Link to="/runs">← {t("back", lang)}</Link>
        </p>
        {error && <div className="error-banner">{error}</div>}
        {run && (
          <>
            <div className="section-head">
              <div>
                <h1>Run #{run.id}</h1>
                <p>
                  {run.source} · LLM {llmLabel}
                  {run.llm_fallback_note ? ` (${run.llm_fallback_note})` : ""}
                </p>
              </div>
              {run.status === "ok" && (
                <button
                  className="btn btn-primary"
                  type="button"
                  disabled={pdfBusy}
                  onClick={handleExportPdf}
                >
                  {pdfBusy ? t("exportPdfBusy", lang) : t("exportPdf", lang)}
                </button>
              )}
            </div>

            <div className="meta-row">
              <div>
                {t("status", lang)}:{" "}
                <strong className={run.status === "ok" ? "status-ok" : "status-err"}>{run.status}</strong>
              </div>
              <div>
                {t("validation", lang)}:{" "}
                <strong className={run.validation_ok ? "status-ok" : "status-err"}>
                  {run.validation_ok ? t("ok", lang) : t("failed", lang)}
                </strong>
              </div>
              {summary?.last_cash != null && (
                <div>
                  {t("lastCash", lang)}:{" "}
                  <strong>{fmtEur(summary.last_cash, lang)}</strong>
                </div>
              )}
              {summary?.open_invoices != null && (
                <div>
                  {t("openInvoices", lang)}: <strong>{summary.open_invoices}</strong>
                </div>
              )}
            </div>

            {run.error_message && <div className="error-banner">{run.error_message}</div>}

            {run.llm_fallback_note && (
              <div className="soft-banner soft-banner-info" role="status">
                <strong>{t("llmFallback", lang)}</strong>
                <span>{run.llm_fallback_note}</span>
              </div>
            )}

            {soft.length > 0 && <SoftWarnings warnings={soft} lang={lang} />}

            {run.comparison?.models && run.comparison.models.length > 0 && (
              <div className="panel">
                <h3>{t("comparison", lang)}</h3>
                <p className="muted">
                  {t("packModel", lang)}: <code>{run.comparison.pack_model || run.llm_model}</code>
                  {run.comparison.recommended_model && (
                    <>
                      {" · "}
                      {t("recommended", lang)}:{" "}
                      <strong className="badge-recommended">
                        {run.comparison.recommended_model}
                      </strong>
                    </>
                  )}
                </p>
                <div className="table-wrap">
                  <table className="data-table compact">
                    <thead>
                      <tr>
                        <th>{t("ollamaModel", lang)}</th>
                        <th className="num">{t("colParam", lang)}</th>
                        <th className="num">{t("colRead", lang)}</th>
                        <th className="num">{t("colMom", lang)}</th>
                        <th className="num">{t("colInterp", lang)}</th>
                        <th>{t("colFi", lang)}</th>
                        <th className="num">{t("colLatency", lang)}</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {run.comparison.models.map((row) => {
                        const isRec = row.model === run.comparison?.recommended_model;
                        const open = expandedAnswer === row.model;
                        return (
                          <Fragment key={row.model}>
                            <tr className={isRec ? "row-recommended" : undefined}>
                              <td>
                                <code>{row.model}</code>
                                {isRec && (
                                  <span className="pill-recommended">{t("recommended", lang)}</span>
                                )}
                              </td>
                              <td className="num">{fmtScore(row.parameter_score)}</td>
                              <td className="num">{fmtScore(row.reading_score)}</td>
                              <td className="num">{fmtScore(row.mom_score)}</td>
                              <td className="num">{fmtScore(row.interpretation_score)}</td>
                              <td>{row.fi_band || fmtScore(row.fi_quality_score)}</td>
                              <td className="num">
                                {row.latency_ms != null
                                  ? `${Math.round(row.latency_ms)} ms`
                                  : "—"}
                              </td>
                              <td>
                                <button
                                  type="button"
                                  className="btn btn-ghost btn-small"
                                  onClick={() =>
                                    setExpandedAnswer(open ? null : row.model)
                                  }
                                >
                                  {open ? t("hideAnswer", lang) : t("showAnswer", lang)}
                                </button>
                              </td>
                            </tr>
                            {open && (
                              <tr>
                                <td colSpan={8}>
                                  <pre className="compare-answer">
                                    {row.interpretation_answer || "—"}
                                  </pre>
                                  {row.notes ? (
                                    <p className="muted">{row.notes}</p>
                                  ) : null}
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {showFromText && (
              <div className="panel">
                <h3>{t("fromTextLabel", lang)}</h3>
                <p className="quote-text">{run.from_text}</p>
              </div>
            )}

            {(params || (summary?.field_summary && summary.field_summary.length > 0)) && (
              <div className="panel">
                <h3>{t("extractedParams", lang)}</h3>
                <div className="summary-cards">
                  {resolveFieldSummary(summary, lang).map((row) => (
                    <div className="summary-card" key={row.input_name}>
                      <div className="summary-label">{row.label}</div>
                      <div className="summary-value">
                        {row.display}
                        {row.source != null && (
                          <span className="summary-hint"> · {row.source}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                {params?.notes != null && String(params.notes) && (
                  <p className="muted pack-note">
                    <strong>{t("paramNotes", lang)}:</strong> {String(params.notes)}
                  </p>
                )}
              </div>
            )}

            {showDescription &&
              (() => {
                const fi = descFi;
                const en = descEn;
                const identical = Boolean(fi && en && fi === en);
                const scenarioLang = String(summary?.language || "").toLowerCase();
                const primaryLabel =
                  scenarioLang === "en" || scenarioLang === "fi"
                    ? scenarioLang.toUpperCase()
                    : lang === "en"
                      ? "EN"
                      : "FI";
                // When from_text equalled description, still show once under Description.
                const heading = fromTextDupesDescription
                  ? t("description", lang)
                  : t("description", lang);

                if (identical || (!fi && en) || (fi && !en)) {
                  return (
                    <div className="panel">
                      <h3>{heading}</h3>
                      <div className="bilingual-block bilingual-block-single">
                        <div>
                          <span className="lang-chip">{primaryLabel}</span>
                          <p>{fi || en}</p>
                        </div>
                      </div>
                    </div>
                  );
                }

                return (
                  <div className="panel">
                    <h3>{heading}</h3>
                    <div className="bilingual-block">
                      <div>
                        <span className="lang-chip">FI</span>
                        <p>{fi}</p>
                      </div>
                      <div>
                        <span className="lang-chip">EN</span>
                        <p>{en}</p>
                      </div>
                    </div>
                  </div>
                );
              })()}

            {summary?.balance_history && summary.balance_history.length > 0 && (
              <div className="panel">
                <h3>{t("cashHistory", lang)}</h3>
                <BalanceHistoryChart data={summary.balance_history} lang={lang} />
              </div>
            )}

            {summary?.projection && summary.projection.length > 0 && (
              <div className="panel">
                <h3>{t("cashProjection", lang)}</h3>
                <ProjectionChart data={summary.projection} lang={lang} />
              </div>
            )}

            {run.validation_json && (
              <ValidationPanel issues={run.validation_json.issues} lang={lang} />
            )}

            <div className="panel">
              <h3>{t("artifacts", lang)}</h3>
              <div className="artifact-list">
                {run.artifacts.map((name) => (
                  <div key={name} className="artifact-row">
                    {name.endsWith(".json") && (
                      <button className="btn btn-primary" type="button" onClick={() => viewJson(name)}>
                        {t("viewPack", lang)}: {name}
                      </button>
                    )}
                    <button
                      className="btn btn-ghost"
                      type="button"
                      onClick={() => api.downloadArtifact(run.id, name)}
                    >
                      {t("download", lang)} {name}
                    </button>
                  </div>
                ))}
              </div>
              {jsonText && jsonName && (
                <div className="artifact-viewer-slot">
                  <ArtifactViewer
                    filename={jsonName}
                    text={jsonText}
                    lang={lang}
                    onClose={() => {
                      setJsonText(null);
                      setJsonName(null);
                    }}
                  />
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {run && run.status === "ok" && (
        <ChatDemo
          runId={run.id}
          lang={lang}
          llmAdapter={run.llm_adapter}
          llmModel={run.llm_model}
        />
      )}
    </div>
  );
}

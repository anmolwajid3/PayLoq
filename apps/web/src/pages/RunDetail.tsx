import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import * as api from "../api";
import type { Run } from "../api";
import { useAuth } from "../auth";
import { ArtifactViewer } from "../components/ArtifactViewer";
import { BalanceHistoryChart, ProjectionChart } from "../components/CashChart";
import { ChatDemo } from "../components/ChatDemo";
import { SoftWarnings, ValidationPanel } from "../components/SoftWarnings";
import { fmtEur, fmtPct } from "../lib/format";
import { t } from "../i18n";

export function RunDetailPage() {
  const { id = "" } = useParams();
  const { lang } = useAuth();
  const [run, setRun] = useState<Run | null>(null);
  const [jsonText, setJsonText] = useState<string | null>(null);
  const [jsonName, setJsonName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [journalBusy, setJournalBusy] = useState(false);

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

  async function buildJournal() {
    if (!run) return;
    setJournalBusy(true);
    setError(null);
    try {
      const updated = await api.ensureJournal(run.id);
      setRun(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setJournalBusy(false);
    }
  }

  if (!run && !error) return <p className="muted">{t("loading", lang)}</p>;

  const summary = run?.pack_summary;
  const soft = summary?.nl_soft_warnings || [];
  const params = summary?.parameters;

  return (
    <div>
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
                {run.source} · LLM {run.llm_adapter}
                {run.llm_fallback_note ? ` (${run.llm_fallback_note})` : ""}
              </p>
            </div>
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

          {run.from_text && (
            <div className="panel">
              <h3>{t("fromTextLabel", lang)}</h3>
              <p className="quote-text">{run.from_text}</p>
            </div>
          )}

          {params && (
            <div className="panel">
              <h3>{t("extractedParams", lang)}</h3>
              <div className="summary-cards">
                <div className="summary-card">
                  <div className="summary-label">{t("revenueStart", lang)}</div>
                  <div className="summary-value">{fmtEur(Number(params.monthly_revenue_start_eur), lang)}</div>
                </div>
                <div className="summary-card">
                  <div className="summary-label">{t("growth", lang)}</div>
                  <div className="summary-value">{fmtPct(Number(params.monthly_revenue_growth), lang)}</div>
                </div>
                <div className="summary-card">
                  <div className="summary-label">{t("targetCash", lang)}</div>
                  <div className="summary-value">{fmtEur(Number(params.target_cash_at_end_eur), lang)}</div>
                </div>
                <div className="summary-card">
                  <div className="summary-label">{t("investment", lang)}</div>
                  <div className="summary-value">{fmtEur(Number(params.special_investment_eur || 0), lang)}</div>
                </div>
              </div>
              {params.notes != null && String(params.notes) && (
                <p className="muted pack-note">
                  <strong>{t("paramNotes", lang)}:</strong> {String(params.notes)}
                </p>
              )}
            </div>
          )}

          {summary?.description && (
            <div className="panel">
              <h3>{t("description", lang)}</h3>
              <div className="bilingual-block">
                <div>
                  <span className="lang-chip">FI</span>
                  <p>{summary.description.fi}</p>
                </div>
                <div>
                  <span className="lang-chip">EN</span>
                  <p>{summary.description.en}</p>
                </div>
              </div>
            </div>
          )}

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

          {run.status === "ok" && <ChatDemo runId={run.id} lang={lang} />}

          {run.validation_json && (
            <ValidationPanel issues={run.validation_json.issues} lang={lang} />
          )}

          <div className="panel">
            <h3>{t("artifacts", lang)}</h3>
            {!run.artifacts.includes("journal_entries.json") && run.status === "ok" && (
              <p>
                <button
                  className="btn btn-ghost"
                  type="button"
                  disabled={journalBusy}
                  onClick={buildJournal}
                >
                  {journalBusy ? t("loading", lang) : t("ensureJournal", lang)}
                </button>
              </p>
            )}
            {run.artifacts.includes("journal_entries.json") && (
              <p className="status-ok">{t("journalReady", lang)}: journal_entries.json</p>
            )}
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
  );
}

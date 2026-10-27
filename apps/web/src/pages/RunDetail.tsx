import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import * as api from "../api";
import type { Run } from "../api";
import { useAuth } from "../auth";
import { BalanceHistoryChart, ProjectionChart } from "../components/CashChart";
import { t } from "../i18n";

export function RunDetailPage() {
  const { id = "" } = useParams();
  const { lang } = useAuth();
  const [run, setRun] = useState<Run | null>(null);
  const [jsonText, setJsonText] = useState<string | null>(null);
  const [jsonName, setJsonName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  if (!run && !error) return <p className="muted">{t("loading", lang)}</p>;

  const summary = run?.pack_summary;

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
              <h1>
                Run #{run.id}
              </h1>
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
                <strong>{Math.round(summary.last_cash).toLocaleString("fi-FI")} €</strong>
              </div>
            )}
            {summary?.open_invoices != null && (
              <div>
                {t("openInvoices", lang)}: <strong>{summary.open_invoices}</strong>
              </div>
            )}
          </div>

          {run.error_message && <div className="error-banner">{run.error_message}</div>}

          {summary?.description && (
            <div className="panel">
              <h3>{t("description", lang)}</h3>
              <p>{lang === "fi" ? summary.description.fi : summary.description.en}</p>
            </div>
          )}

          {summary?.balance_history && summary.balance_history.length > 0 && (
            <div className="panel">
              <h3>{t("cashHistory", lang)}</h3>
              <BalanceHistoryChart data={summary.balance_history} />
            </div>
          )}

          {summary?.projection && summary.projection.length > 0 && (
            <div className="panel">
              <h3>{t("cashProjection", lang)}</h3>
              <ProjectionChart data={summary.projection} />
            </div>
          )}

          {run.validation_json && (
            <div className="panel">
              <h3>{t("validation", lang)}</h3>
              {run.validation_json.issues.length === 0 && <p className="status-ok">{t("ok", lang)}</p>}
              {run.validation_json.issues.map((issue) => (
                <div key={`${issue.code}-${issue.message}`} className={`issue ${issue.severity}`}>
                  [{issue.severity}] {issue.code}: {issue.message}
                </div>
              ))}
            </div>
          )}

          <div className="panel">
            <h3>{t("artifacts", lang)}</h3>
            <div className="artifact-list">
              {run.artifacts.map((name) => (
                <div key={name} style={{ display: "flex", gap: "0.4rem" }}>
                  {name.endsWith(".json") && (
                    <button className="btn btn-ghost" type="button" onClick={() => viewJson(name)}>
                      {t("viewJson", lang)}: {name}
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
            {jsonText && (
              <div style={{ marginTop: "1rem" }}>
                <h3>{jsonName}</h3>
                <pre className="json-view">{jsonText}</pre>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

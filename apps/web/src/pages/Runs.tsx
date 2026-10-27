import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as api from "../api";
import type { Run } from "../api";
import { useAuth } from "../auth";
import { t } from "../i18n";

export function RunsPage() {
  const { lang } = useAuth();
  const [rows, setRows] = useState<Run[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listRuns()
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : "Error"));
  }, []);

  return (
    <div>
      <div className="section-head">
        <div>
          <h1>{t("runs", lang)}</h1>
          <p className="muted">JSON · Excel · validation · charts</p>
        </div>
      </div>
      {error && <div className="error-banner">{error}</div>}
      {!rows.length && !error && <p className="muted">{t("emptyRuns", lang)}</p>}
      <div className="scenario-list">
        {rows.map((r) => (
          <Link key={r.id} className="scenario-row" to={`/runs/${r.id}`}>
            <div>
              <h2>
                #{r.id} · {r.source}
                <span className="badge">{r.llm_adapter}</span>
              </h2>
              <p>
                {t("status", lang)}:{" "}
                <span className={r.status === "ok" ? "status-ok" : "status-err"}>{r.status}</span>
                {r.pack_summary?.last_cash != null &&
                  ` · ${t("lastCash", lang)}: ${Math.round(r.pack_summary.last_cash).toLocaleString("fi-FI")} €`}
              </p>
            </div>
            <span className="muted">{t("open", lang)} →</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

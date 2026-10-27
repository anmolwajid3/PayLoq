import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as api from "../api";
import type { Scenario } from "../api";
import { useAuth } from "../auth";
import { t } from "../i18n";

export function ScenariosPage() {
  const { lang } = useAuth();
  const [rows, setRows] = useState<Scenario[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listScenarios()
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : "Error"));
  }, []);

  return (
    <div>
      <div className="section-head">
        <div>
          <h1>{t("scenarios", lang)}</h1>
          <p className="muted">good · weak · cash_critical</p>
        </div>
        <Link className="btn btn-primary" to="/generate">
          {t("generate", lang)}
        </Link>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <div className="scenario-list">
        {rows.map((s) => (
          <Link key={s.id} className="scenario-row" to={`/scenarios/${s.slug}`}>
            <div>
              <h2>
                {lang === "fi" ? s.title_fi : s.title_en}
                {s.is_preset && <span className="badge">{t("preset", lang)}</span>}
              </h2>
              <p>{lang === "fi" ? s.description_fi : s.description_en}</p>
            </div>
            <span className="muted">{t("open", lang)} →</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

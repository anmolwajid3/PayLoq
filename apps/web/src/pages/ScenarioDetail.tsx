import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import * as api from "../api";
import type { Scenario } from "../api";
import { useAuth } from "../auth";
import { ArtifactViewer } from "../components/ArtifactViewer";
import { t } from "../i18n";

export function ScenarioDetailPage() {
  const { slug = "" } = useParams();
  const { lang } = useAuth();
  const navigate = useNavigate();
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .getScenario(slug)
      .then(setScenario)
      .catch((e) => setError(e instanceof Error ? e.message : "Error"));
  }, [slug]);

  async function onGenerate() {
    setBusy(true);
    setError(null);
    try {
      const run = await api.generatePreset(slug);
      navigate(`/runs/${run.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  if (!scenario && !error) return <p className="muted">{t("loading", lang)}</p>;

  return (
    <div>
      <p>
        <Link to="/scenarios">← {t("back", lang)}</Link>
      </p>
      {error && <div className="error-banner">{error}</div>}
      {scenario && (
        <>
          <div className="section-head">
            <div>
              <h1>
                {lang === "fi" ? scenario.title_fi : scenario.title_en}
                {scenario.is_preset && <span className="badge">{t("preset", lang)}</span>}
              </h1>
              <div className="bilingual-block">
                <div>
                  <span className="lang-chip">FI</span>
                  <p>{scenario.description_fi}</p>
                </div>
                <div>
                  <span className="lang-chip">EN</span>
                  <p>{scenario.description_en}</p>
                </div>
              </div>
            </div>
            <button className="btn btn-primary" type="button" disabled={busy} onClick={onGenerate}>
              {t("generatePreset", lang)}
            </button>
          </div>
          <div className="panel">
            <ArtifactViewer
              filename="input.json"
              text={JSON.stringify(scenario.input_json, null, 2)}
              lang={lang}
            />
          </div>
        </>
      )}
    </div>
  );
}

import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import { useAuth } from "../auth";
import { t } from "../i18n";

export function GeneratePage() {
  const { lang } = useAuth();
  const navigate = useNavigate();
  const [text, setText] = useState(
    "Pieni konepaja, kassa on kriittinen kolmen viikon päästä.",
  );
  const [llm, setLlm] = useState<"stub" | "ollama">("stub");
  const [language, setLanguage] = useState<"fi" | "en">("fi");
  const [months, setMonths] = useState(12);
  const [industry, setIndustry] = useState("metal workshop (machine shop)");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const run = await api.generateFromText({
        text,
        llm,
        language,
        industry,
        months,
      });
      navigate(`/runs/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="section-head">
        <div>
          <h1>{t("fromText", lang)}</h1>
          <p className="muted">stub / Ollama → params → pack</p>
        </div>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <form className="form" onSubmit={onSubmit}>
        <label>
          {t("description", lang)}
          <textarea value={text} onChange={(e) => setText(e.target.value)} required />
        </label>
        <label>
          LLM
          <select value={llm} onChange={(e) => setLlm(e.target.value as "stub" | "ollama")}>
            <option value="stub">{t("llmStub", lang)}</option>
            <option value="ollama">{t("llmOllama", lang)}</option>
          </select>
        </label>
        <label>
          {t("language", lang)}
          <select value={language} onChange={(e) => setLanguage(e.target.value as "fi" | "en")}>
            <option value="fi">FI</option>
            <option value="en">EN</option>
          </select>
        </label>
        <label>
          {t("months", lang)}
          <input
            type="number"
            min={12}
            max={24}
            value={months}
            onChange={(e) => setMonths(Number(e.target.value))}
          />
        </label>
        <label>
          {t("industry", lang)}
          <input value={industry} onChange={(e) => setIndustry(e.target.value)} />
        </label>
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? t("loading", lang) : t("runGenerate", lang)}
        </button>
      </form>
    </div>
  );
}

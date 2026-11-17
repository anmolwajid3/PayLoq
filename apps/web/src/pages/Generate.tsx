import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import { useAuth } from "../auth";
import { t } from "../i18n";

const DEFAULT_INDUSTRY = "metal workshop (machine shop)";
const FI_DESC_PLACEHOLDER =
  "Pieni konepaja, kassa on kriittinen kolmen viikon päästä.";
const EN_DESC_PLACEHOLDER =
  "Small machine shop; cash is critical within three weeks.";

export function GeneratePage() {
  const { lang } = useAuth();
  const navigate = useNavigate();
  // Empty by default — example text lives in the placeholder so it is clearly editable.
  const [text, setText] = useState("");
  const [llm, setLlm] = useState<"stub" | "ollama">("stub");
  // Scenario language follows UI language; user can still override.
  const [language, setLanguage] = useState<"fi" | "en">(lang);
  const [months, setMonths] = useState(12);
  const [industry, setIndustry] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLanguage(lang);
  }, [lang]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const run = await api.generateFromText({
        text: text.trim(),
        llm,
        language,
        industry: industry.trim() || DEFAULT_INDUSTRY,
        months,
      });
      navigate(`/runs/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  const descPlaceholder = language === "en" ? EN_DESC_PLACEHOLDER : FI_DESC_PLACEHOLDER;

  return (
    <div>
      <div className="section-head">
        <div>
          <h1>{t("fromText", lang)}</h1>
          <p className="muted">{t("fromTextHint", lang)}</p>
        </div>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <form className="form" onSubmit={onSubmit}>
        <label>
          {t("description", lang)}
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={descPlaceholder}
            required
          />
          <span className="field-hint">{t("descriptionHint", lang)}</span>
        </label>
        <label>
          LLM
          <select
            value={llm}
            onChange={(e) => setLlm(e.target.value as "stub" | "ollama")}
            aria-label="LLM"
          >
            {/* Hardcoded labels so Docker/i18n never show a truncated or wrong option. */}
            <option value="stub">Stub (CPU)</option>
            <option value="ollama">Ollama</option>
          </select>
          <span className="field-hint">{t("llmHint", lang)}</span>
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
            step={1}
            value={months}
            onChange={(e) => setMonths(Number(e.target.value))}
          />
          <span className="field-hint">{t("monthsHint", lang)}</span>
        </label>
        <label>
          {t("industry", lang)}
          <input
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            placeholder={DEFAULT_INDUSTRY}
          />
          <span className="field-hint">{t("industryHint", lang)}</span>
        </label>
        <button className="btn btn-primary" type="submit" disabled={busy || !text.trim()}>
          {busy ? t("loading", lang) : t("runGenerate", lang)}
        </button>
      </form>
    </div>
  );
}

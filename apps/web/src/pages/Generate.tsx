import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import type { OllamaModel } from "../api";
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
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [modelsAvailable, setModelsAvailable] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [recommended, setRecommended] = useState<string[]>([]);
  const [model, setModel] = useState("");
  // Scenario language follows UI language; user can still override.
  const [language, setLanguage] = useState<"fi" | "en">(lang);
  const [months, setMonths] = useState(12);
  const [industry, setIndustry] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingModels, setLoadingModels] = useState(true);

  useEffect(() => {
    setLanguage(lang);
  }, [lang]);

  useEffect(() => {
    setLoadingModels(true);
    api
      .listLlmModels()
      .then((res) => {
        setModels(res.models);
        setModelsAvailable(res.available);
        setModelsError(res.error);
        setRecommended(res.recommended || []);
        const names = res.models.map((m) => m.name);
        const preferred =
          names.find((n) => n === "llama3.2:1b" || n.startsWith("llama3.2:1b")) ||
          names.find((n) => n.includes("qwen2.5:0.5b")) ||
          names[0] ||
          "";
        setModel(preferred);
      })
      .catch((e) => {
        setModels([]);
        setModelsAvailable(false);
        setModelsError(e instanceof Error ? e.message : "Error");
      })
      .finally(() => setLoadingModels(false));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!model) {
      setError(
        lang === "fi"
          ? "Valitse paikallinen Ollama-malli. Lataa malli: docker compose --profile ollama …"
          : "Pick a local Ollama model. Pull one with docker compose --profile ollama …",
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const run = await api.generateFromText({
        text: text.trim(),
        llm: "ollama",
        ollama_model: model,
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
          {t("ollamaModel", lang)}
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            aria-label={t("ollamaModel", lang)}
            disabled={loadingModels || models.length === 0}
            required
          >
            {models.length === 0 ? (
              <option value="">{t("noModels", lang)}</option>
            ) : (
              models.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name}
                  {m.parameter_size ? ` (${m.parameter_size})` : ""}
                </option>
              ))
            )}
          </select>
          <span className="field-hint">{t("llmHint", lang)}</span>
          {!loadingModels && (!modelsAvailable || models.length === 0) && (
            <span className="field-hint warn-hint">
              {modelsError
                ? `${t("ollamaUnavailable", lang)}: ${modelsError}`
                : t("ollamaUnavailable", lang)}
              {recommended.length > 0 && (
                <>
                  {" "}
                  {t("pullHint", lang)}:{" "}
                  <code>{recommended.slice(0, 3).join(", ")}</code>
                </>
              )}
            </span>
          )}
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
        <button
          className="btn btn-primary"
          type="submit"
          disabled={busy || !text.trim() || !model || models.length === 0}
        >
          {busy ? t("loading", lang) : t("runGenerate", lang)}
        </button>
      </form>
    </div>
  );
}

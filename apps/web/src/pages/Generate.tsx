import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api";
import type { OllamaModel } from "../api";
import { useAuth } from "../auth";
import { t } from "../i18n";

const FI_DESC_PLACEHOLDER =
  "Pieni konepaja, kassa on kriittinen kolmen viikon päästä.";
const EN_DESC_PLACEHOLDER =
  "Small machine shop; cash is critical within three weeks.";

const FALLBACK_SHORTLIST = ["qwen2.5:3b", "llama3.2:3b", "qwen2.5:7b"];

function tagInstalled(names: string[], tag: string): boolean {
  if (names.includes(tag)) return true;
  if (!tag.includes(":") && names.includes(`${tag}:latest`)) return true;
  return false;
}

export function GeneratePage() {
  const { lang } = useAuth();
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [modelsAvailable, setModelsAvailable] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [recommended, setRecommended] = useState<string[]>([]);
  const [shortlist, setShortlist] = useState<string[]>(FALLBACK_SHORTLIST);
  const [model, setModel] = useState("");
  const [compareSelected, setCompareSelected] = useState<string[]>([]);
  const [language, setLanguage] = useState<"fi" | "en">(lang);
  const [months, setMonths] = useState(12);
  const [industry, setIndustry] = useState("");
  const [companySize, setCompanySize] = useState("");
  const [seed, setSeed] = useState(42);
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
        const sl = res.compare_shortlist?.length
          ? res.compare_shortlist
          : FALLBACK_SHORTLIST;
        setShortlist(sl);
        const names = res.models.map((m) => m.name);
        const preferred =
          names.find((n) => n === "qwen2.5:7b" || n.startsWith("qwen2.5:7b")) ||
          names.find((n) => n.includes("qwen2.5:7b")) ||
          names.find((n) => n.includes("qwen2.5:3b")) ||
          names[0] ||
          "";
        setModel(preferred);
        const defaults = sl.filter((tag) => tagInstalled(names, tag));
        const withPrimary =
          preferred && !defaults.includes(preferred)
            ? [preferred, ...defaults]
            : defaults.length
              ? defaults
              : preferred
                ? [preferred]
                : [];
        setCompareSelected(withPrimary);
      })
      .catch((e) => {
        setModels([]);
        setModelsAvailable(false);
        setModelsError(e instanceof Error ? e.message : "Error");
      })
      .finally(() => setLoadingModels(false));
  }, []);

  function toggleCompare(tag: string) {
    setCompareSelected((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );
  }

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
    if (!companySize.trim()) {
      setError(t("companySizeMissing", lang));
      return;
    }
    if (months < 12 || months > 24) {
      setError(
        lang === "fi"
          ? "Kuukausien on oltava välillä 12–24."
          : "Months must be between 12 and 24.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const compareTags = Array.from(
        new Set([model, ...compareSelected.filter(Boolean)]),
      );
      const run = await api.generateFromText({
        text: text.trim(),
        llm: "ollama",
        ollama_model: model,
        language,
        industry: industry.trim() || "unspecified",
        company_size: companySize.trim(),
        months,
        seed,
        compare: true,
        compare_models: compareTags,
        background: true,
      });
      // Navigate immediately; Run detail polls progress while status is running.
      navigate(`/runs/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  const descPlaceholder = language === "en" ? EN_DESC_PLACEHOLDER : FI_DESC_PLACEHOLDER;
  const installedNames = models.map((m) => m.name);
  const compareChoices = Array.from(
    new Set([...shortlist, ...installedNames.filter((n) => shortlist.some((s) => n.includes(s.split(":")[0])))]),
  ).filter((tag) => tagInstalled(installedNames, tag));

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
            onChange={(e) => {
              const next = e.target.value;
              setModel(next);
              setCompareSelected((prev) =>
                next && !prev.includes(next) ? [next, ...prev] : prev,
              );
            }}
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
        {compareChoices.length > 0 && (
          <fieldset className="compare-fieldset">
            <legend>{t("compareModels", lang)}</legend>
            <span className="field-hint">{t("compareModelsHint", lang)}</span>
            <div className="compare-checks">
              {compareChoices.map((tag) => (
                <label key={tag} className="compare-check">
                  <input
                    type="checkbox"
                    checked={compareSelected.includes(tag)}
                    onChange={() => toggleCompare(tag)}
                  />
                  <span>{tag}</span>
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <label>
          {t("language", lang)}
          <select value={language} onChange={(e) => setLanguage(e.target.value as "fi" | "en")}>
            <option value="fi">FI</option>
            <option value="en">EN</option>
          </select>
        </label>
        <label>
          {t("industry", lang)}
          <input
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            placeholder="e.g. metal workshop, bakery, hotel"
          />
          <span className="field-hint">{t("industryHint", lang)}</span>
        </label>
        <label>
          {t("companySize", lang)}
          <input
            value={companySize}
            onChange={(e) => setCompanySize(e.target.value)}
            placeholder="small | medium | large | 8 | 420 | 12 employees"
            required
            aria-label={t("companySize", lang)}
          />
          <span className="field-hint">{t("companySizeHint", lang)}</span>
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
          {t("seed", lang)}
          <input
            type="number"
            step={1}
            value={seed}
            onChange={(e) => setSeed(Number(e.target.value))}
            aria-label={t("seed", lang)}
          />
          <span className="field-hint">{t("seedHint", lang)}</span>
        </label>
        <button
          className="btn btn-primary"
          type="submit"
          disabled={busy || !text.trim() || !model || models.length === 0 || !companySize.trim()}
        >
          {busy ? t("startingBackground", lang) : t("runGenerate", lang)}
        </button>
      </form>
    </div>
  );
}

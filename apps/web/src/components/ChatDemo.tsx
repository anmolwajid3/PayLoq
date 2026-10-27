import { useEffect, useState } from "react";
import * as api from "../api";
import type { ChatPreset, ChatResponse } from "../api";
import type { Lang } from "../i18n";
import { t } from "../i18n";

type Props = {
  runId: number;
  lang: Lang;
};

export function ChatDemo({ runId, lang }: Props) {
  const [presets, setPresets] = useState<ChatPreset[]>([]);
  const [preset, setPreset] = useState<"cash_drop" | "cash_negative" | "">("cash_drop");
  const [custom, setCustom] = useState("");
  const [llm, setLlm] = useState<"stub" | "ollama">("stub");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [showFigures, setShowFigures] = useState(false);

  useEffect(() => {
    api
      .listChatPresets(lang)
      .then((rows) => {
        setPresets(rows);
        if (rows[0]?.id === "cash_drop" || rows[0]?.id === "cash_negative") {
          setPreset(rows[0].id);
        }
      })
      .catch(() => setPresets([]));
  }, [lang]);

  async function ask() {
    setBusy(true);
    setError(null);
    try {
      const body: Parameters<typeof api.chatOnRun>[1] = {
        language: lang,
        llm,
      };
      if (custom.trim()) {
        body.question = custom.trim();
      } else if (preset) {
        body.preset = preset;
      } else {
        throw new Error(lang === "fi" ? "Valitse valmis kysymys tai kirjoita oma." : "Pick a preset or type a question.");
      }
      const res = await api.chatOnRun(runId, body);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel chat-panel">
      <h3>{t("chatDemo", lang)}</h3>
      <p className="muted">{t("chatHint", lang)}</p>

      <div className="chat-controls">
        <label>
          {t("llmStub", lang)} / {t("llmOllama", lang)}
          <select value={llm} onChange={(e) => setLlm(e.target.value as "stub" | "ollama")}>
            <option value="stub">{t("llmStub", lang)}</option>
            <option value="ollama">{t("llmOllama", lang)}</option>
          </select>
        </label>

        <div className="preset-row" role="group" aria-label={t("chatDemo", lang)}>
          {presets.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`btn btn-ghost ${preset === p.id && !custom.trim() ? "active-preset" : ""}`}
              onClick={() => {
                setPreset(p.id as "cash_drop" | "cash_negative");
                setCustom("");
              }}
            >
              {p.question}
            </button>
          ))}
        </div>

        <label>
          {t("customQuestion", lang)}
          <input
            type="text"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder={lang === "fi" ? "Esim. Miksi kassa laski?" : "e.g. Why did cash drop?"}
          />
        </label>

        <button className="btn" type="button" onClick={ask} disabled={busy}>
          {busy ? t("loading", lang) : t("ask", lang)}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {result && (
        <div className="chat-result">
          <p className="muted">
            LLM: {result.llm_adapter}
            {result.fallback_note ? ` · ${result.fallback_note}` : ""}
          </p>
          <p>
            <strong>Q:</strong> {result.question}
          </p>
          <h4>{t("answer", lang)}</h4>
          <pre className="chat-answer">{result.answer}</pre>
          <button
            className="btn btn-ghost"
            type="button"
            onClick={() => setShowFigures((v) => !v)}
          >
            {showFigures ? t("hideFigures", lang) : t("showFigures", lang)}
          </button>
          {showFigures && (
            <pre className="json-view">{JSON.stringify(result.figures, null, 2)}</pre>
          )}
        </div>
      )}
    </div>
  );
}

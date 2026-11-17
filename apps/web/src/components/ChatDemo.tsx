import { useEffect, useRef, useState } from "react";
import * as api from "../api";
import type { ChatPreset, ChatResponse } from "../api";
import type { Lang } from "../i18n";
import { t } from "../i18n";
import { fmtEur } from "../lib/format";

type Props = {
  runId: number;
  lang: Lang;
  llmAdapter: string;
  llmModel: string | null;
};

type HistoryItem = {
  id: string;
  at: string;
  kind: "preset" | "custom";
  presetId: string | null;
  question: string;
  answer: string;
  figures: Record<string, unknown>;
  llm_adapter: string;
  llm_model: string | null;
  fallback_note: string | null;
};

const PRESET_META: Record<
  string,
  { icon: string; sparkKeys: string[] }
> = {
  cash_drop: {
    icon: "↓",
    sparkKeys: [
      "balance_history_change",
      "mom_cash_change",
      "special_investment_eur",
      "largest_weekly_cash_drops",
    ],
  },
  cash_negative: {
    icon: "⚠",
    sparkKeys: [
      "first_negative_date",
      "first_negative_balance",
      "first_negative_projection_week",
      "first_negative_projection_balance",
    ],
  },
};

function historyKey(runId: number) {
  return `payloq_chat_history_${runId}`;
}

function loadHistory(runId: number): HistoryItem[] {
  try {
    const raw = sessionStorage.getItem(historyKey(runId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as HistoryItem[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveHistory(runId: number, items: HistoryItem[]) {
  sessionStorage.setItem(historyKey(runId), JSON.stringify(items));
}

function sparkValues(
  figures: Record<string, unknown>,
  keys: string[],
  lang: Lang,
): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];
  for (const key of keys) {
    const v = figures[key];
    if (v == null) continue;
    if (typeof v === "number") {
      const isMoney =
        key.includes("cash") ||
        key.includes("balance") ||
        key.includes("investment") ||
        key.includes("eur");
      out.push({
        label: key.replace(/_/g, " "),
        value: isMoney ? fmtEur(v, lang) : String(v),
      });
    } else if (typeof v === "string" || typeof v === "number") {
      out.push({ label: key.replace(/_/g, " "), value: String(v) });
    } else if (Array.isArray(v) && v.length > 0 && key === "largest_weekly_cash_drops") {
      const top = v[0] as { delta?: number; to_date?: string };
      if (typeof top?.delta === "number") {
        out.push({
          label: lang === "fi" ? "suurin viikkomuutos" : "largest weekly drop",
          value: `${fmtEur(top.delta, lang)}${top.to_date ? ` → ${top.to_date}` : ""}`,
        });
      }
    }
    if (out.length >= 3) break;
  }
  return out;
}

function toHistoryItem(res: ChatResponse, kind: "preset" | "custom"): HistoryItem {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    at: new Date().toISOString(),
    kind,
    presetId: res.preset,
    question: res.question,
    answer: res.answer,
    figures: res.figures,
    llm_adapter: res.llm_adapter,
    llm_model: res.llm_model,
    fallback_note: res.fallback_note,
  };
}

/** Company-style sidebar chat bound to the run's generate-time model. */
export function ChatDemo({ runId, lang, llmAdapter, llmModel }: Props) {
  const [presets, setPresets] = useState<ChatPreset[]>([]);
  const [preset, setPreset] = useState<"cash_drop" | "cash_negative" | "">("cash_drop");
  const [custom, setCustom] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>(() => loadHistory(runId));
  const [expandedFigures, setExpandedFigures] = useState<string | null>(null);
  const [open, setOpen] = useState(true);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setHistory(loadHistory(runId));
  }, [runId]);

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

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history, busy]);

  async function ask(nextPreset?: "cash_drop" | "cash_negative" | null) {
    setBusy(true);
    setError(null);
    try {
      const body: Parameters<typeof api.chatOnRun>[1] = { language: lang };
      const customQ = custom.trim();
      let kind: "preset" | "custom" = "custom";
      if (customQ && nextPreset == null) {
        body.question = customQ;
        kind = "custom";
      } else {
        const pid = nextPreset || preset;
        if (!pid) {
          throw new Error(
            lang === "fi" ? "Valitse valmis kysymys tai kirjoita oma." : "Pick a preset or type a question.",
          );
        }
        body.preset = pid;
        kind = "preset";
      }
      const res = await api.chatOnRun(runId, body);
      const item = toHistoryItem(res, kind);
      setHistory((prev) => {
        const next = [...prev, item];
        saveHistory(runId, next);
        return next;
      });
      if (kind === "custom") setCustom("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  function clearHistory() {
    setHistory([]);
    sessionStorage.removeItem(historyKey(runId));
  }

  const modelLabel = llmModel
    ? `${llmAdapter} · ${llmModel}`
    : llmAdapter;

  return (
    <aside className={`run-chat-sidebar ${open ? "open" : "collapsed"}`} aria-label={t("chatTitle", lang)}>
      <div className="run-chat-head">
        <div>
          <h3>{t("chatTitle", lang)}</h3>
          <p className="muted run-chat-model">
            {t("chatUsesModel", lang)}: <strong>{modelLabel}</strong>
          </p>
        </div>
        <button
          type="button"
          className="btn btn-ghost chat-toggle"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          {open ? "⟩" : "⟨"}
        </button>
      </div>

      {open && (
        <>
          <p className="muted chat-sidebar-hint">{t("chatHint", lang)}</p>

          <div className="chat-thread" role="log" aria-live="polite">
            {history.length === 0 && (
              <p className="muted chat-empty">{t("chatEmpty", lang)}</p>
            )}
            {history.map((item) => {
              const meta = item.presetId ? PRESET_META[item.presetId] : null;
              const sparks = meta
                ? sparkValues(item.figures, meta.sparkKeys, lang)
                : sparkValues(item.figures, ["special_investment_eur", "cash_end", "balance_history_change"], lang);
              return (
                <div key={item.id} className="chat-turn">
                  <div className="chat-bubble chat-bubble-user">
                    <div className="chat-chip-row">
                      {item.kind === "preset" && item.presetId ? (
                        <span className="chat-chip chat-chip-preset">
                          <span className="chat-chip-icon" aria-hidden>
                            {PRESET_META[item.presetId]?.icon || "?"}
                          </span>
                          {t("presetUsed", lang)}: {item.presetId}
                        </span>
                      ) : (
                        <span className="chat-chip chat-chip-custom">
                          <span className="chat-chip-icon" aria-hidden>
                            ✎
                          </span>
                          {t("customUsed", lang)}
                        </span>
                      )}
                    </div>
                    <p>{item.question}</p>
                  </div>
                  <div className="chat-bubble chat-bubble-assistant">
                    <pre className="chat-answer">{item.answer}</pre>
                    {sparks.length > 0 && (
                      <div className="chat-sparks" aria-label={t("figureSparks", lang)}>
                        {sparks.map((s) => (
                          <span key={s.label} className="chat-spark">
                            <span className="chat-spark-dot" aria-hidden />
                            <span className="chat-spark-label">{s.label}</span>
                            <strong>{s.value}</strong>
                          </span>
                        ))}
                      </div>
                    )}
                    <button
                      className="btn btn-ghost"
                      type="button"
                      onClick={() =>
                        setExpandedFigures((cur) => (cur === item.id ? null : item.id))
                      }
                    >
                      {expandedFigures === item.id ? t("hideFigures", lang) : t("showFigures", lang)}
                    </button>
                    {expandedFigures === item.id && (
                      <pre className="json-view">{JSON.stringify(item.figures, null, 2)}</pre>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={bottomRef} />
          </div>

          <div className="chat-composer">
            <div className="preset-row" role="group" aria-label={t("chatTitle", lang)}>
              {presets.map((p) => {
                const meta = PRESET_META[p.id];
                const active = preset === p.id && !custom.trim();
                return (
                  <button
                    key={p.id}
                    type="button"
                    className={`btn btn-ghost preset-chip ${active ? "active-preset" : ""}`}
                    onClick={() => {
                      setPreset(p.id as "cash_drop" | "cash_negative");
                      setCustom("");
                      void ask(p.id as "cash_drop" | "cash_negative");
                    }}
                    disabled={busy}
                    title={p.question}
                  >
                    <span className="chat-chip-icon" aria-hidden>
                      {meta?.icon || "?"}
                    </span>
                    {p.question}
                  </button>
                );
              })}
            </div>

            <label className="chat-custom-label">
              {t("customQuestion", lang)}
              <div className="chat-input-row">
                <input
                  type="text"
                  value={custom}
                  onChange={(e) => setCustom(e.target.value)}
                  placeholder={lang === "fi" ? "Esim. Miksi kassa laski?" : "e.g. Why did cash drop?"}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !busy && custom.trim()) {
                      e.preventDefault();
                      void ask(null);
                    }
                  }}
                />
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={() => void ask(null)}
                  disabled={busy || !custom.trim()}
                >
                  {busy ? t("loading", lang) : t("ask", lang)}
                </button>
              </div>
            </label>

            {history.length > 0 && (
              <button className="btn btn-ghost" type="button" onClick={clearHistory}>
                {t("clearChat", lang)}
              </button>
            )}

            {error && <div className="error-banner">{error}</div>}
          </div>
        </>
      )}
    </aside>
  );
}

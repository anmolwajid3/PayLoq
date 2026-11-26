import { useCallback, useEffect, useState, type FormEvent } from "react";
import * as api from "../api";
import type { CompanySession } from "../api";
import { useAuth } from "../auth";
import { t } from "../i18n";

export function CompanyDataPage() {
  const { lang } = useAuth();
  const [session, setSession] = useState<CompanySession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [question, setQuestion] = useState("");
  const [files, setFiles] = useState<FileList | null>(null);

  const refresh = useCallback(() => {
    api
      .getCompanySession()
      .then(setSession)
      .catch(() => setSession(null));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onUpload(e: FormEvent) {
    e.preventDefault();
    if (!files || files.length === 0) {
      setError(lang === "fi" ? "Valitse tiedosto(t)." : "Pick file(s).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await api.uploadCompanyFiles(Array.from(files));
      setSession(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function onReport() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.companySituationReport({ language: lang });
      setSession(res.session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function onChat(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.companyChat({
        question: question.trim(),
        language: lang,
      });
      setSession(res.session);
      setQuestion("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function onDiscard() {
    setBusy(true);
    setError(null);
    try {
      await api.discardCompanySession();
      setSession(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function onPdf() {
    if (!session) return;
    const { exportCompanyChatPdf } = await import("../lib/exportCompanyChatPdf");
    exportCompanyChatPdf(session, lang);
  }

  return (
    <div>
      <div className="section-head">
        <div>
          <h1>{t("companyData", lang)}</h1>
          <p className="muted">{t("companyDataHint", lang)}</p>
        </div>
      </div>
      {error && <div className="error-banner">{error}</div>}

      <form className="form" onSubmit={onUpload}>
        <label>
          {t("uploadFiles", lang)}
          <input
            type="file"
            multiple
            accept=".xlsx,.xlsm,.csv,.json"
            onChange={(e) => setFiles(e.target.files)}
          />
          <span className="field-hint">{t("uploadFilesHint", lang)}</span>
        </label>
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? t("loading", lang) : t("upload", lang)}
        </button>
      </form>

      {session && (
        <div className="panel" style={{ marginTop: "1.25rem" }}>
          <h3>{t("sessionActive", lang)}</h3>
          <p className="muted">
            {t("expiresIn", lang)}: {Math.round(session.ttl_remaining_s / 60)} min ·{" "}
            {session.filenames.join(", ")}
            {session.model ? ` · ${t("chatUsesModel", lang)} ${session.model}` : ""}
          </p>
          <div className="artifact-list" style={{ marginBottom: "0.75rem" }}>
            <button className="btn btn-primary" type="button" disabled={busy} onClick={onReport}>
              {t("situationReport", lang)}
            </button>
            <button className="btn" type="button" disabled={busy} onClick={onPdf}>
              {t("exportChatPdf", lang)}
            </button>
            <button className="btn btn-ghost" type="button" disabled={busy} onClick={onDiscard}>
              {t("discardSession", lang)}
            </button>
          </div>

          {session.situation_report && (
            <div className="soft-banner soft-banner-info" role="status">
              <strong>{t("situationReport", lang)}</strong>
              <p style={{ whiteSpace: "pre-wrap", margin: "0.4rem 0 0" }}>
                {session.situation_report}
              </p>
            </div>
          )}

          <div className="chat-log">
            {session.chat.map((turn, i) => (
              <div
                key={`${turn.at}-${i}`}
                className={
                  turn.role === "user" ? "chat-bubble chat-bubble-user" : "chat-bubble chat-bubble-assistant"
                }
              >
                <strong>{turn.role === "user" ? t("customQuestion", lang) : t("answer", lang)}</strong>
                <p style={{ whiteSpace: "pre-wrap" }}>{turn.content}</p>
              </div>
            ))}
          </div>

          <form className="form" onSubmit={onChat}>
            <label>
              {t("customQuestion", lang)}
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={3}
              />
            </label>
            <button className="btn btn-primary" type="submit" disabled={busy || !question.trim()}>
              {t("ask", lang)}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

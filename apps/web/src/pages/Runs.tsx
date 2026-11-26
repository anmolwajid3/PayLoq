import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import * as api from "../api";
import type { Run } from "../api";
import { useAuth } from "../auth";
import { fmtEur } from "../lib/format";
import { t } from "../i18n";

const PAGE_SIZE = 10;

export function RunsPage() {
  const { lang } = useAuth();
  const navigate = useNavigate();
  const [rows, setRows] = useState<Run[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "ok" | "error" | "running">("all");
  const [sourceFilter, setSourceFilter] = useState<"all" | "from_text" | "preset">("all");
  const [page, setPage] = useState(1);

  function reload() {
    api
      .listRuns(200)
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : "Error"));
  }

  useEffect(() => {
    reload();
  }, []);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter((r) => {
      if (statusFilter !== "all" && r.status !== statusFilter) return false;
      if (sourceFilter !== "all" && r.source !== sourceFilter) return false;
      if (!needle) return true;
      const blob = [
        String(r.id),
        r.source,
        r.status,
        r.llm_adapter,
        r.llm_model || "",
        r.from_text || "",
        r.pack_summary?.scenario || "",
        r.error_message || "",
      ]
        .join(" ")
        .toLowerCase();
      return blob.includes(needle);
    });
  }, [rows, q, statusFilter, sourceFilter]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageSafe = Math.min(page, pageCount);
  const pageRows = filtered.slice((pageSafe - 1) * PAGE_SIZE, pageSafe * PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [q, statusFilter, sourceFilter]);

  async function onPdf(run: Run) {
    if (run.status !== "ok") return;
    setBusyId(run.id);
    setError(null);
    try {
      const { exportRunPdf } = await import("../lib/exportRunPdf");
      exportRunPdf(run, lang);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusyId(null);
    }
  }

  async function onDelete(run: Run) {
    const ok = window.confirm(
      lang === "fi" ? `Poistetaanko ajo #${run.id}?` : `Delete run #${run.id}?`,
    );
    if (!ok) return;
    setBusyId(run.id);
    setError(null);
    try {
      await api.deleteRun(run.id);
      setRows((prev) => prev.filter((r) => r.id !== run.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusyId(null);
    }
  }

  function onEditRegenerate(run: Run) {
    if (run.source === "preset" && run.pack_summary?.scenario) {
      navigate(`/scenarios/${run.pack_summary.scenario}`);
      return;
    }
    navigate("/generate", { state: { fromRun: run } });
  }

  return (
    <div>
      <div className="section-head">
        <div>
          <h1>{t("runs", lang)}</h1>
          <p className="muted">{t("runsHint", lang)}</p>
        </div>
        <Link className="btn btn-primary" to="/generate">
          {t("generate", lang)}
        </Link>
      </div>
      {error && <div className="error-banner">{error}</div>}

      <div className="list-toolbar">
        <input
          className="list-search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("search", lang)}
          aria-label={t("search", lang)}
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
          aria-label={t("status", lang)}
        >
          <option value="all">{t("filterAll", lang)}</option>
          <option value="ok">ok</option>
          <option value="error">error</option>
          <option value="running">running</option>
        </select>
        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value as typeof sourceFilter)}
          aria-label={t("source", lang)}
        >
          <option value="all">{t("filterAll", lang)}</option>
          <option value="from_text">from_text</option>
          <option value="preset">preset</option>
        </select>
        <span className="muted list-count">
          {filtered.length} / {rows.length}
        </span>
      </div>

      {!filtered.length && !error && <p className="muted">{t("emptyRuns", lang)}</p>}

      {filtered.length > 0 && (
        <div className="table-wrap panel">
          <table className="data-table compact">
            <thead>
              <tr>
                <th>#</th>
                <th>{t("source", lang)}</th>
                <th>{t("status", lang)}</th>
                <th>{t("ollamaModel", lang)}</th>
                <th>{t("lastCash", lang)}</th>
                <th>{t("created", lang)}</th>
                <th>{t("actions", lang)}</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((r) => {
                const llm = r.llm_model
                  ? `${r.llm_adapter} · ${r.llm_model}`
                  : r.llm_adapter;
                const created = r.created_at
                  ? new Date(r.created_at).toLocaleString(
                      lang === "fi" ? "fi-FI" : "en-IE",
                    )
                  : "—";
                return (
                  <tr key={r.id}>
                    <td>
                      <Link to={`/runs/${r.id}`}>#{r.id}</Link>
                    </td>
                    <td>
                      <code>{r.source}</code>
                    </td>
                    <td>
                      <span
                        className={
                          r.status === "ok"
                            ? "status-ok"
                            : r.status === "running" || r.status === "pending"
                              ? "status-running"
                              : "status-err"
                        }
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="muted">{llm}</td>
                    <td className="num">
                      {r.pack_summary?.last_cash != null
                        ? fmtEur(r.pack_summary.last_cash, lang)
                        : "—"}
                    </td>
                    <td className="muted">{created}</td>
                    <td>
                      <div className="row-actions">
                        <Link className="btn btn-ghost btn-small" to={`/runs/${r.id}`}>
                          {t("open", lang)}
                        </Link>
                        <button
                          type="button"
                          className="btn btn-ghost btn-small"
                          disabled={busyId === r.id}
                          onClick={() => onEditRegenerate(r)}
                        >
                          {t("editRegenerate", lang)}
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-small"
                          disabled={busyId === r.id || r.status !== "ok"}
                          onClick={() => onPdf(r)}
                        >
                          {t("exportPdf", lang)}
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-small"
                          disabled={busyId === r.id}
                          onClick={() => onDelete(r)}
                        >
                          {t("delete", lang)}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {pageCount > 1 && (
        <div className="pagination">
          <button
            type="button"
            className="btn btn-ghost btn-small"
            disabled={pageSafe <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            ←
          </button>
          <span className="muted">
            {pageSafe} / {pageCount}
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-small"
            disabled={pageSafe >= pageCount}
            onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
          >
            →
          </button>
        </div>
      )}
    </div>
  );
}

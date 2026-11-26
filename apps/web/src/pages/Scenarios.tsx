import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { jsPDF } from "jspdf";
import * as api from "../api";
import type { Scenario } from "../api";
import { useAuth } from "../auth";
import { t } from "../i18n";

const PAGE_SIZE = 10;

function exportScenarioPdf(s: Scenario, lang: "fi" | "en") {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const margin = 14;
  const maxW = 210 - margin * 2;
  let y = margin;
  const write = (text: string, bold = false, size = 10) => {
    doc.setFont("helvetica", bold ? "bold" : "normal");
    doc.setFontSize(size);
    const lines = doc.splitTextToSize(text || "—", maxW) as string[];
    for (const line of lines) {
      if (y > 280) {
        doc.addPage();
        y = margin;
      }
      doc.text(line, margin, y);
      y += size * 0.45;
    }
    y += 2;
  };
  const title = lang === "fi" ? s.title_fi : s.title_en;
  write("PayLoq", true, 16);
  write(title, true, 13);
  write(`slug: ${s.slug}${s.is_preset ? " · preset" : ""}`, false, 9);
  write(t("description", lang), true, 11);
  write(lang === "fi" ? s.description_fi : s.description_en, false, 9);
  write("FI", true, 10);
  write(s.description_fi, false, 8);
  write("EN", true, 10);
  write(s.description_en, false, 8);
  doc.save(`payloq-scenario-${s.slug}.pdf`);
}

export function ScenariosPage() {
  const { lang } = useAuth();
  const navigate = useNavigate();
  const [rows, setRows] = useState<Scenario[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busySlug, setBusySlug] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState<"all" | "preset" | "custom">("all");
  const [page, setPage] = useState(1);

  useEffect(() => {
    api
      .listScenarios()
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : "Error"));
  }, []);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter((s) => {
      if (kind === "preset" && !s.is_preset) return false;
      if (kind === "custom" && s.is_preset) return false;
      if (!needle) return true;
      const blob = [
        s.slug,
        s.title_fi,
        s.title_en,
        s.description_fi,
        s.description_en,
      ]
        .join(" ")
        .toLowerCase();
      return blob.includes(needle);
    });
  }, [rows, q, kind]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageSafe = Math.min(page, pageCount);
  const pageRows = filtered.slice((pageSafe - 1) * PAGE_SIZE, pageSafe * PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [q, kind]);

  async function onGenerate(s: Scenario) {
    setBusySlug(s.slug);
    setError(null);
    try {
      const run = await api.generatePreset(s.slug, {
        language: lang,
        compare: true,
        background: true,
      });
      navigate(`/runs/${run.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusySlug(null);
    }
  }

  return (
    <div>
      <div className="section-head">
        <div>
          <h1>{t("scenarios", lang)}</h1>
          <p className="muted">{t("scenariosHint", lang)}</p>
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
          value={kind}
          onChange={(e) => setKind(e.target.value as typeof kind)}
          aria-label={t("preset", lang)}
        >
          <option value="all">{t("filterAll", lang)}</option>
          <option value="preset">{t("preset", lang)}</option>
          <option value="custom">{t("customScenario", lang)}</option>
        </select>
        <span className="muted list-count">
          {filtered.length} / {rows.length}
        </span>
      </div>

      {!filtered.length && !error && <p className="muted">{t("emptyScenarios", lang)}</p>}

      {filtered.length > 0 && (
        <div className="table-wrap panel">
          <table className="data-table compact">
            <thead>
              <tr>
                <th>{t("scenario", lang)}</th>
                <th>Slug</th>
                <th>{t("type", lang)}</th>
                <th>{t("description", lang)}</th>
                <th>{t("actions", lang)}</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((s) => {
                const title = lang === "fi" ? s.title_fi : s.title_en;
                const desc = lang === "fi" ? s.description_fi : s.description_en;
                return (
                  <tr key={s.id}>
                    <td>
                      <Link to={`/scenarios/${s.slug}`}>{title}</Link>
                    </td>
                    <td>
                      <code>{s.slug}</code>
                    </td>
                    <td>
                      {s.is_preset ? (
                        <span className="badge">{t("preset", lang)}</span>
                      ) : (
                        t("customScenario", lang)
                      )}
                    </td>
                    <td className="muted desc-cell">{desc}</td>
                    <td>
                      <div className="row-actions">
                        <Link
                          className="btn btn-ghost btn-small"
                          to={`/scenarios/${s.slug}`}
                        >
                          {t("open", lang)}
                        </Link>
                        <button
                          type="button"
                          className="btn btn-ghost btn-small"
                          disabled={busySlug === s.slug}
                          onClick={() => onGenerate(s)}
                        >
                          {busySlug === s.slug
                            ? t("startingBackground", lang)
                            : t("generatePreset", lang)}
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-small"
                          onClick={() => exportScenarioPdf(s, lang)}
                        >
                          {t("exportPdf", lang)}
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

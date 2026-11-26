import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import type { Run } from "../api";
import type { Lang } from "../i18n";
import { t } from "../i18n";
import { fmtEur } from "./format";
import { resolveFieldSummary } from "./fieldSummary";

type Series = { label: string; values: number[]; color: [number, number, number] };

type PdfDoc = jsPDF & {
  lastAutoTable?: { finalY: number };
};

const MARGIN = 14;
const PAGE_W = 210;
const CONTENT_W = PAGE_W - MARGIN * 2;

function softMessage(
  w: {
    code: string;
    message_fi?: string;
    message_en?: string;
    message?: string;
  },
  lang: Lang,
): string {
  return (
    (lang === "fi" ? w.message_fi : w.message_en) ||
    w.message ||
    w.message_en ||
    w.message_fi ||
    w.code
  );
}

function ensureSpace(doc: PdfDoc, y: number, needed: number): number {
  const pageH = doc.internal.pageSize.getHeight();
  if (y + needed > pageH - 14) {
    doc.addPage();
    return MARGIN;
  }
  return y;
}

function sectionTitle(doc: PdfDoc, title: string, y: number): number {
  y = ensureSpace(doc, y, 12);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(12);
  doc.setTextColor(20, 60, 55);
  doc.text(title, MARGIN, y);
  return y + 6;
}

function bodyText(doc: PdfDoc, text: string, y: number, maxWidth = CONTENT_W): number {
  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(40, 40, 40);
  const lines = doc.splitTextToSize(text || "—", maxWidth) as string[];
  for (const line of lines) {
    y = ensureSpace(doc, y, 5);
    doc.text(line, MARGIN, y);
    y += 4.5;
  }
  return y + 2;
}

function drawLineChart(
  doc: PdfDoc,
  y: number,
  title: string,
  xLabels: string[],
  series: Series[],
  lang: Lang,
): number {
  const chartH = 48;
  const chartW = CONTENT_W;
  const leftPad = 18;
  const bottomPad = 10;
  const topPad = 6;
  const plotW = chartW - leftPad - 4;
  const plotH = chartH - topPad - bottomPad;

  y = sectionTitle(doc, title, y);
  y = ensureSpace(doc, y, chartH + 14);

  const allVals = series.flatMap((s) => s.values);
  if (!allVals.length || !xLabels.length) {
    return bodyText(doc, "—", y);
  }

  let minV = Math.min(...allVals, 0);
  let maxV = Math.max(...allVals, 0);
  if (minV === maxV) {
    maxV = minV + 1;
  }
  const span = maxV - minV;

  const originX = MARGIN + leftPad;
  const originY = y + topPad + plotH;

  doc.setDrawColor(200, 210, 208);
  doc.setLineWidth(0.2);
  doc.rect(originX, y + topPad, plotW, plotH);

  // Zero line when range crosses zero
  if (minV < 0 && maxV > 0) {
    const zy = originY - ((0 - minV) / span) * plotH;
    doc.setDrawColor(180, 180, 180);
    doc.setLineDashPattern([1, 1], 0);
    doc.line(originX, zy, originX + plotW, zy);
    doc.setLineDashPattern([], 0);
  }

  const n = Math.max(xLabels.length - 1, 1);
  for (const s of series) {
    doc.setDrawColor(...s.color);
    doc.setLineWidth(0.7);
    for (let i = 0; i < s.values.length - 1; i++) {
      const x1 = originX + (i / n) * plotW;
      const x2 = originX + ((i + 1) / n) * plotW;
      const y1 = originY - ((s.values[i] - minV) / span) * plotH;
      const y2 = originY - ((s.values[i + 1] - minV) / span) * plotH;
      doc.line(x1, y1, x2, y2);
    }
  }

  doc.setFont("helvetica", "normal");
  doc.setFontSize(7);
  doc.setTextColor(90, 90, 90);
  doc.text(`${Math.round(maxV / 1000)}k`, MARGIN, y + topPad + 2);
  doc.text(`${Math.round(minV / 1000)}k`, MARGIN, originY);

  const labelStep = Math.max(1, Math.ceil(xLabels.length / 8));
  for (let i = 0; i < xLabels.length; i += labelStep) {
    const x = originX + (i / n) * plotW;
    doc.text(xLabels[i], x, originY + 5, { align: i === 0 ? "left" : "center" });
  }

  // Legend
  let lx = MARGIN;
  const ly = originY + 10;
  for (const s of series) {
    doc.setFillColor(...s.color);
    doc.rect(lx, ly - 2.2, 3.5, 3.5, "F");
    doc.setTextColor(50, 50, 50);
    doc.text(s.label, lx + 5, ly + 0.8);
    lx += doc.getTextWidth(s.label) + 12;
  }

  // Min/max caption for single-series cash charts
  if (series.length === 1) {
    const vals = series[0].values;
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    doc.setFontSize(8);
    doc.setTextColor(80, 80, 80);
    doc.text(
      `${fmtEur(min, lang)} – ${fmtEur(max, lang)}`,
      MARGIN + chartW,
      ly + 0.8,
      { align: "right" },
    );
  }

  return ly + 8;
}

/**
 * Build a standalone PDF summary for a completed run.
 * Charts are drawn as vector polylines from pack_summary data (no DOM capture).
 */
export function buildRunPdf(run: Run, lang: Lang): jsPDF {
  const doc = new jsPDF({ unit: "mm", format: "a4" }) as PdfDoc;
  const summary = run.pack_summary;
  const params = summary?.parameters;
  let y = MARGIN;

  // Header
  doc.setFont("helvetica", "bold");
  doc.setFontSize(16);
  doc.setTextColor(18, 55, 52);
  doc.text("PayLoq", MARGIN, y);
  y += 7;
  doc.setFontSize(13);
  doc.text(`${t("exportPdfTitle", lang)} #${run.id}`, MARGIN, y);
  y += 6;
  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(90, 90, 90);
  const llmLabel = run.llm_model ? `${run.llm_adapter} · ${run.llm_model}` : run.llm_adapter;
  const created = run.created_at
    ? new Date(run.created_at).toLocaleString(lang === "fi" ? "fi-FI" : "en-IE")
    : "";
  doc.text(
    `${run.source} · LLM ${llmLabel}${created ? ` · ${created}` : ""}`,
    MARGIN,
    y,
  );
  y += 8;

  // Key figures
  y = sectionTitle(doc, t("keyFigures", lang), y);
  const figureRows: string[][] = [
    [t("status", lang), run.status],
    [
      t("validation", lang),
      run.validation_ok ? t("ok", lang) : t("failed", lang),
    ],
  ];
  if (summary?.scenario) figureRows.push([t("scenario", lang), String(summary.scenario)]);
  if (summary?.months != null) figureRows.push([t("months", lang), String(summary.months)]);
  if (summary?.as_of) figureRows.push([t("asOf", lang), String(summary.as_of)]);
  if (summary?.last_cash != null) {
    figureRows.push([t("lastCash", lang), fmtEur(summary.last_cash, lang)]);
  }
  if (summary?.last_revenue != null) {
    figureRows.push([t("lastRevenue", lang), fmtEur(summary.last_revenue, lang)]);
  }
  if (summary?.open_invoices != null) {
    figureRows.push([t("openInvoices", lang), String(summary.open_invoices)]);
  }
  if (summary?.projection?.length) {
    const minProj = Math.min(...summary.projection.map((p) => p.projected_balance));
    figureRows.push([t("minProjection", lang), fmtEur(minProj, lang)]);
  }
  if (run.seed != null) figureRows.push([t("seed", lang), String(run.seed)]);

  autoTable(doc, {
    startY: y,
    margin: { left: MARGIN, right: MARGIN },
    tableWidth: CONTENT_W,
    theme: "plain",
    styles: { fontSize: 9, cellPadding: 1.5, textColor: [40, 40, 40] },
    columnStyles: {
      0: { fontStyle: "bold", cellWidth: 55 },
      1: { cellWidth: CONTENT_W - 55 },
    },
    body: figureRows,
  });
  y = (doc.lastAutoTable?.finalY ?? y) + 6;

  if (run.llm_fallback_note) {
    y = sectionTitle(doc, t("llmFallback", lang), y);
    y = bodyText(doc, run.llm_fallback_note, y);
  }

  if (run.error_message) {
    y = sectionTitle(doc, t("error", lang), y);
    y = bodyText(doc, run.error_message, y);
  }

  // Soft warnings
  const soft = summary?.nl_soft_warnings || [];
  if (soft.length) {
    y = sectionTitle(doc, t("softWarnings", lang), y);
    y = bodyText(doc, t("softWarningsHint", lang), y);
    autoTable(doc, {
      startY: y,
      margin: { left: MARGIN, right: MARGIN },
      tableWidth: CONTENT_W,
      head: [[t("type", lang), t("description", lang)]],
      body: soft.map((w) => [w.code, softMessage(w, lang)]),
      styles: { fontSize: 8, cellPadding: 1.5, overflow: "linebreak" },
      headStyles: { fillColor: [232, 220, 170], textColor: [40, 40, 40] },
      columnStyles: { 0: { cellWidth: 40 }, 1: { cellWidth: CONTENT_W - 40 } },
    });
    y = (doc.lastAutoTable?.finalY ?? y) + 6;
  }

  // Input text
  const fromText = (run.from_text || "").trim();
  if (fromText) {
    y = sectionTitle(doc, t("fromTextLabel", lang), y);
    y = bodyText(doc, fromText, y);
  }

  // Extracted parameters — every field-map row (generic display).
  const fieldRows = resolveFieldSummary(summary, lang);
  if (fieldRows.length || params) {
    y = sectionTitle(doc, t("extractedParams", lang), y);
    const paramRows: string[][] = fieldRows.map((row) => {
      const src = row.source ? ` (${row.source})` : "";
      return [row.label, `${row.display}${src}`];
    });

    if (params?.notes != null && String(params.notes).trim()) {
      paramRows.push([t("paramNotes", lang), String(params.notes)]);
    }

    if (paramRows.length) {
      autoTable(doc, {
        startY: y,
        margin: { left: MARGIN, right: MARGIN },
        tableWidth: CONTENT_W,
        theme: "striped",
        styles: { fontSize: 8, cellPadding: 1.5, overflow: "linebreak" },
        headStyles: { fillColor: [18, 63, 60], textColor: [255, 255, 255] },
        columnStyles: { 0: { cellWidth: 55, fontStyle: "bold" }, 1: { cellWidth: CONTENT_W - 55 } },
        body: paramRows,
      });
      y = (doc.lastAutoTable?.finalY ?? y) + 6;
    }
  }

  // Description
  const descFi = (summary?.description?.fi || "").trim();
  const descEn = (summary?.description?.en || "").trim();
  if (descFi || descEn) {
    y = sectionTitle(doc, t("description", lang), y);
    if (descFi && descEn && descFi !== descEn) {
      y = bodyText(doc, `FI: ${descFi}`, y);
      y = bodyText(doc, `EN: ${descEn}`, y);
    } else {
      y = bodyText(doc, descFi || descEn, y);
    }
  }

  // Cash history chart
  const history = summary?.balance_history || [];
  if (history.length) {
    y = drawLineChart(
      doc,
      y,
      t("cashHistory", lang),
      history.map((h) => h.date.slice(5)), // MM-DD
      [
        {
          label: t("cash", lang),
          values: history.map((h) => h.balance),
          color: [212, 160, 23],
        },
      ],
      lang,
    );
  }

  // Projection chart + compact table
  const projection = summary?.projection || [];
  if (projection.length) {
    y = drawLineChart(
      doc,
      y,
      t("cashProjection", lang),
      projection.map((p) => `W${p.week}`),
      [
        {
          label: t("projectedBalance", lang),
          values: projection.map((p) => p.projected_balance),
          color: [61, 191, 143],
        },
        {
          label: t("salesInflow", lang),
          values: projection.map((p) => p.sales_inflow),
          color: [200, 170, 60],
        },
        {
          label: t("purchaseOutflow", lang),
          values: projection.map((p) => p.purchase_outflow),
          color: [224, 112, 96],
        },
      ],
      lang,
    );

    y = ensureSpace(doc, y, 20);
    autoTable(doc, {
      startY: y,
      margin: { left: MARGIN, right: MARGIN },
      tableWidth: CONTENT_W,
      head: [
        [
          t("week", lang),
          t("weekEnd", lang),
          t("projectedBalance", lang),
          t("salesInflow", lang),
          t("purchaseOutflow", lang),
        ],
      ],
      body: projection.map((p) => [
        String(p.week),
        p.week_end,
        fmtEur(p.projected_balance, lang),
        fmtEur(p.sales_inflow, lang),
        fmtEur(p.purchase_outflow, lang),
      ]),
      styles: { fontSize: 7.5, cellPadding: 1.2 },
      headStyles: { fillColor: [18, 63, 60], textColor: [255, 255, 255] },
      didParseCell: (data) => {
        if (data.section === "body" && data.column.index === 2) {
          const raw = projection[data.row.index]?.projected_balance;
          if (raw != null && raw < 0) {
            data.cell.styles.textColor = [180, 40, 40];
            data.cell.styles.fontStyle = "bold";
          }
        }
      },
    });
    y = (doc.lastAutoTable?.finalY ?? y) + 6;
  }

  // Validation
  const issues = run.validation_json?.issues || [];
  y = sectionTitle(doc, t("validation", lang), y);
  if (!issues.length) {
    y = bodyText(doc, t("noIssues", lang), y);
  } else {
    autoTable(doc, {
      startY: y,
      margin: { left: MARGIN, right: MARGIN },
      tableWidth: CONTENT_W,
      head: [[t("type", lang), "Code", t("description", lang)]],
      body: issues.map((issue) => [
        issue.severity === "error" ? t("severityError", lang) : t("severityWarning", lang),
        issue.code,
        issue.message,
      ]),
      styles: { fontSize: 8, cellPadding: 1.5, overflow: "linebreak" },
      headStyles: { fillColor: [18, 63, 60], textColor: [255, 255, 255] },
      columnStyles: {
        0: { cellWidth: 22 },
        1: { cellWidth: 36 },
        2: { cellWidth: CONTENT_W - 58 },
      },
    });
    y = (doc.lastAutoTable?.finalY ?? y) + 6;
  }

  // Model comparison + judge (PL-53)
  const cmp = run.comparison;
  if (cmp?.models?.length) {
    y = sectionTitle(doc, t("comparison", lang), y);
    y = bodyText(
      doc,
      `${t("packModel", lang)}: ${cmp.pack_model || run.llm_model || "—"}` +
        (cmp.recommended_model
          ? ` · ${t("recommended", lang)}: ${cmp.recommended_model}`
          : ""),
      y,
    );
    if (cmp.judge_model || cmp.judge_models?.length || cmp.judge_skipped) {
      const judges =
        cmp.judge_models && cmp.judge_models.length > 0
          ? cmp.judge_models.join(", ")
          : cmp.judge_model || "—";
      y = bodyText(
        doc,
        cmp.judge_skipped
          ? `${t("judgeModel", lang)}: — (${cmp.judge_skipped})`
          : `${t("judgePanel", lang)}: ${judges}`,
        y,
      );
      if (cmp.judge_dashboard?.length) {
        const dash = cmp.judge_dashboard
          .map(
            (j) =>
              `${j.judge_model}=${
                j.mean_score == null ? "—" : Number(j.mean_score).toFixed(2)
              }`,
          )
          .join(" · ");
        y = bodyText(doc, `${t("judgeDashboard", lang)}: ${dash}`, y);
      }
    }
    if (cmp.score_weights) {
      const w = cmp.score_weights;
      y = bodyText(
        doc,
        `${t("scoreWeights", lang)}: param ${w.parameter ?? "—"} · read ${w.reading ?? "—"} · MoM ${w.mom ?? "—"} · interp ${w.interpretation ?? "—"} · FI ${w.fi_quality ?? "—"}`,
        y,
      );
    }
    autoTable(doc, {
      startY: y,
      margin: { left: MARGIN, right: MARGIN },
      tableWidth: CONTENT_W,
      head: [
        [
          t("ollamaModel", lang),
          t("colParam", lang),
          t("colRead", lang),
          t("colMom", lang),
          t("colInterp", lang),
          t("colJudge", lang),
          t("colFi", lang),
          "Comp",
        ],
      ],
      body: cmp.models.map((row) => [
        row.model === cmp.recommended_model ? `${row.model} ★` : row.model,
        row.parameter_score != null ? row.parameter_score.toFixed(2) : "—",
        row.reading_score != null ? row.reading_score.toFixed(2) : "—",
        row.mom_score != null ? row.mom_score.toFixed(2) : "—",
        row.interpretation_score != null ? row.interpretation_score.toFixed(2) : "—",
        row.judge_score != null ? row.judge_score.toFixed(2) : "—",
        row.fi_band || (row.fi_quality_score != null ? row.fi_quality_score.toFixed(2) : "—"),
        row.composite_score != null ? row.composite_score.toFixed(2) : "—",
      ]),
      styles: { fontSize: 7, cellPadding: 1.1, overflow: "linebreak" },
      headStyles: { fillColor: [18, 63, 60], textColor: [255, 255, 255] },
    });
    y = (doc.lastAutoTable?.finalY ?? y) + 4;

    for (const row of cmp.models) {
      y = sectionTitle(doc, `${t("modelDetail", lang)}: ${row.model}`, y);
      if (row.score_rationale) {
        y = bodyText(doc, `${t("scoreRationale", lang)}: ${row.score_rationale}`, y);
      }
      if (row.judge_axes && Object.keys(row.judge_axes).length) {
        const axes = Object.entries(row.judge_axes)
          .map(([k, v]) => `${k}=${Number(v).toFixed(2)}`)
          .join(" · ");
        y = bodyText(doc, `${t("judgeAxes", lang)}: ${axes}`, y);
      }
      if (row.judge_notes) {
        y = bodyText(doc, `${t("judgeNotes", lang)}: ${row.judge_notes}`, y);
      }
      if (row.interpretation_answer) {
        y = bodyText(doc, `${t("answer", lang)}: ${row.interpretation_answer}`, y);
      }
    }
  }

  // Artifact inventory + note that JSON tables above are the package content
  y = sectionTitle(doc, t("artifacts", lang), y);
  if (!run.artifacts.length) {
    y = bodyText(doc, "—", y);
  } else {
    autoTable(doc, {
      startY: y,
      margin: { left: MARGIN, right: MARGIN },
      tableWidth: CONTENT_W,
      body: run.artifacts.map((name, i) => [String(i + 1), name]),
      theme: "plain",
      styles: { fontSize: 8, cellPadding: 1.2 },
      columnStyles: { 0: { cellWidth: 10 }, 1: { cellWidth: CONTENT_W - 10 } },
    });
    y = (doc.lastAutoTable?.finalY ?? y) + 4;
    y = bodyText(doc, t("exportPdfArtifactsNote", lang), y);
  }

  // Footer on each page
  const pageCount = doc.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    doc.setFontSize(7);
    doc.setTextColor(140, 140, 140);
    doc.text(
      `PayLoq · run #${run.id} · ${i}/${pageCount}`,
      PAGE_W / 2,
      doc.internal.pageSize.getHeight() - 6,
      { align: "center" },
    );
  }

  return doc;
}

/** Build and download a standalone PDF summary for a completed run. */
export function exportRunPdf(run: Run, lang: Lang): void {
  const doc = buildRunPdf(run, lang);
  doc.save(`payloq-run-${run.id}-results.pdf`);
}

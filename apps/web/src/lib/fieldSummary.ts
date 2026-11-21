import fieldMapJson from "./field_map.json";
import type { Lang } from "../i18n";
import { fmtEur, fmtNum, fmtPct } from "./format";

export type FieldMapRow = {
  input_name: string;
  output_location: string;
  display_label: { en: string; fi: string; [k: string]: string };
  fidelity_rule: string;
  format: string;
  engine_keys?: string[];
  components?: string[];
};

export type FieldSummaryRow = {
  input_name: string;
  output_location: string;
  label: string;
  label_en?: string;
  label_fi?: string;
  value: unknown;
  display: string;
  source?: string | null;
  format?: string;
};

const FIELD_MAP: FieldMapRow[] = (fieldMapJson as { fields: FieldMapRow[] }).fields;

export function getFieldMap(): FieldMapRow[] {
  return FIELD_MAP;
}

function readLocation(
  params: Record<string, unknown> | undefined,
  options: Record<string, unknown> | undefined,
  location: string,
): unknown {
  const parts = location.split(".");
  const root = parts[0];
  let cur: unknown =
    root === "options" ? options || {} : params || {};
  for (const part of parts.slice(1)) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

function formatValue(row: FieldMapRow, value: unknown, lang: Lang): string {
  if (value == null) return "—";
  if (row.format === "eur") {
    const n = Number(value);
    return Number.isFinite(n) ? fmtEur(n, lang) : String(value);
  }
  if (row.format === "fraction") {
    const n = Number(value);
    return Number.isFinite(n) ? fmtPct(n, lang) : String(value);
  }
  if (row.format === "percent") {
    const n = Number(value);
    return Number.isFinite(n) ? `${fmtNum(n, lang, 1)}%` : String(value);
  }
  if (row.format === "days") {
    const n = Number(value);
    return Number.isFinite(n) ? `${fmtNum(n, lang, 0)} ${lang === "fi" ? "pv" : "days"}` : String(value);
  }
  if (row.format === "count") {
    const n = Number(value);
    return Number.isFinite(n) ? fmtNum(n, lang, 0) : String(value);
  }
  if (row.format === "one_off_events") {
    if (!Array.isArray(value) || value.length === 0) return "—";
    return value
      .map((ev) => {
        const e = ev as Record<string, unknown>;
        const amt = Number(e.amount_eur);
        const amtS = Number.isFinite(amt) ? fmtEur(amt, lang) : String(e.amount_eur);
        return `${amtS} · month ${e.month_index} · ${e.direction}`;
      })
      .join("; ");
  }
  return String(value);
}

/** Build Run summary rows from the single field-map config (no hard-coded labels). */
export function buildFieldSummaryFromMap(
  params: Record<string, unknown> | undefined,
  options: Record<string, unknown> | undefined,
  lang: Lang,
): FieldSummaryRow[] {
  const sources = (params?.field_sources || {}) as Record<string, string>;
  return FIELD_MAP.map((row) => {
    const value = readLocation(params, options, row.output_location);
    const label = row.display_label[lang] || row.display_label.en || row.input_name;
    const keys = [row.output_location.split(".").pop()!, row.input_name, ...(row.engine_keys || [])];
    let source: string | null | undefined;
    let sawDerived = false;
    let sawOther: string | null = null;
    for (const key of keys) {
      if (sources[key] === "stated") {
        source = "stated";
        break;
      }
      if (sources[key] === "derived") sawDerived = true;
      else if (sources[key] != null && sawOther == null) sawOther = sources[key];
    }
    if (source == null) source = sawDerived ? "derived" : sawOther;
    return {
      input_name: row.input_name,
      output_location: row.output_location,
      label,
      label_en: row.display_label.en,
      label_fi: row.display_label.fi,
      value,
      display: formatValue(row, value, lang),
      source,
      format: row.format,
    };
  });
}

/** Prefer server-built field_summary; fall back to local map copy. */
export function resolveFieldSummary(
  summary: {
    field_summary?: FieldSummaryRow[];
    parameters?: Record<string, unknown>;
    options?: Record<string, unknown>;
  } | null | undefined,
  lang: Lang,
): FieldSummaryRow[] {
  if (summary?.field_summary && summary.field_summary.length > 0) {
    return summary.field_summary.map((row) => ({
      ...row,
      label:
        lang === "fi"
          ? row.label_fi || row.label
          : row.label_en || row.label,
    }));
  }
  return buildFieldSummaryFromMap(summary?.parameters, summary?.options, lang);
}

/**
 * Smoke-test PDF builder in Node.
 * Run: npx tsx scripts/smoke-export-pdf.ts
 */
import { writeFileSync, statSync, readFileSync } from "node:fs";
import { buildRunPdf } from "../src/lib/exportRunPdf";
import type { Run } from "../src/api";

const run: Run = {
  id: 42,
  scenario_id: 1,
  source: "preset",
  llm_adapter: "stub",
  llm_model: null,
  llm_fallback_note: null,
  seed: 42,
  status: "ok",
  error_message: null,
  artifact_dir: "/tmp",
  validation_ok: true,
  validation_json: {
    ok: true,
    issues: [{ code: "VR-08", message: "Projection move large", severity: "warning" }],
  },
  pack_summary: {
    scenario: "good_steady",
    months: 12,
    as_of: "2025-12-31",
    last_cash: 125000,
    last_revenue: 48000,
    open_invoices: 7,
    balance_history: [
      { date: "2025-01-07", balance: 80000 },
      { date: "2025-02-07", balance: 90000 },
      { date: "2025-03-07", balance: 95000 },
      { date: "2025-04-07", balance: 110000 },
      { date: "2025-05-07", balance: 125000 },
    ],
    projection: [
      {
        week: 1,
        week_end: "2026-01-07",
        sales_inflow: 12000,
        purchase_outflow: 8000,
        projected_balance: 129000,
      },
      {
        week: 2,
        week_end: "2026-01-14",
        sales_inflow: 10000,
        purchase_outflow: 15000,
        projected_balance: 124000,
      },
      {
        week: 3,
        week_end: "2026-01-21",
        sales_inflow: 5000,
        purchase_outflow: 20000,
        projected_balance: -1000,
      },
    ],
    description: {
      fi: "Vakaa kassavirta ja maltillinen kasvu.",
      en: "Steady cash flow and moderate growth.",
    },
    language: "fi",
    parameters: {
      monthly_revenue_start_eur: 40000,
      monthly_revenue_growth: 0.02,
      target_cash_at_end_eur: 120000,
      special_investment_eur: 0,
      days_sales_outstanding: 30,
      days_payables_outstanding: 25,
      cost_shares_of_revenue: {
        materials: 0.35,
        services: 0.15,
        personnel: 0.35,
        other: 0.15,
      },
      notes: "Smoke test notes",
    },
    nl_soft_warnings: [
      {
        code: "SOFT_GROWTH",
        severity: "warning",
        message_fi: "Kasvu vaikuttaa korkealta.",
        message_en: "Growth looks high.",
      },
    ],
  },
  from_text: null,
  created_at: new Date().toISOString(),
  artifacts: ["input.json", "cash_and_invoices.json", "monthly_reports.json"],
};

const doc = buildRunPdf(run, "fi");
const outPdf = "/tmp/payloq-run-42-results.pdf";
const buf = Buffer.from(doc.output("arraybuffer"));
writeFileSync(outPdf, buf);
console.log(`wrote ${outPdf} (${buf.length} bytes)`);

const size = statSync(outPdf).size;
if (size < 1000) throw new Error(`PDF too small: ${size}`);
const head = readFileSync(outPdf).subarray(0, 5).toString("utf8");
if (head !== "%PDF-") throw new Error(`Not a PDF: ${head}`);
console.log("smoke ok");

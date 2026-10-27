import { Fragment, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Lang } from "../i18n";
import { t } from "../i18n";
import { fmtEur, fmtNum, fmtPct } from "../lib/format";
import { BalanceHistoryChart, ProjectionChart } from "./CashChart";

const tooltipStyle = {
  background: "#123f3c",
  border: "1px solid rgba(232,242,239,0.12)",
  borderRadius: 4,
  color: "#e8f2ef",
};

type Props = {
  filename: string;
  text: string;
  lang: Lang;
  onClose?: () => void;
};

function detectKind(filename: string, data: unknown): string {
  const name = filename.toLowerCase();
  if (name.includes("cash_and_invoices")) return "cash";
  if (name.includes("monthly_reports")) return "monthly";
  if (name.includes("journal_entries")) return "journal";
  if (name.includes("input")) return "input";
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>;
    if (o.balance_history && o.open_invoices) return "cash";
    if (Array.isArray(o.months)) return "monthly";
    if (Array.isArray(o.entries)) return "journal";
    if (o.parameters_from_language_model || o.scenario_description) return "input";
  }
  return "generic";
}

export function ArtifactViewer({ filename, text, lang, onClose }: Props) {
  const [tab, setTab] = useState<"view" | "json">("view");
  const parsed = useMemo(() => {
    try {
      return { data: JSON.parse(text) as unknown, error: null as string | null };
    } catch (e) {
      return { data: null, error: e instanceof Error ? e.message : "JSON error" };
    }
  }, [text]);

  const kind = parsed.data ? detectKind(filename, parsed.data) : "generic";

  return (
    <div className="artifact-viewer">
      <div className="artifact-viewer-head">
        <div>
          <h3 className="artifact-title">{filename}</h3>
          <p className="muted">{t("visualView", lang)}</p>
        </div>
        <div className="tab-row" role="tablist">
          <button
            type="button"
            role="tab"
            className={`tab-btn ${tab === "view" ? "active" : ""}`}
            aria-selected={tab === "view"}
            onClick={() => setTab("view")}
          >
            {t("tabView", lang)}
          </button>
          <button
            type="button"
            role="tab"
            className={`tab-btn ${tab === "json" ? "active" : ""}`}
            aria-selected={tab === "json"}
            onClick={() => setTab("json")}
          >
            {t("tabJson", lang)}
          </button>
          {onClose && (
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              {t("close", lang)}
            </button>
          )}
        </div>
      </div>

      {parsed.error && <div className="error-banner">{parsed.error}</div>}

      {tab === "json" ? <pre className="json-view">{text}</pre> : null}

      {tab === "view" && parsed.data != null && kind === "cash" ? (
        <CashPackView data={parsed.data as CashPack} lang={lang} />
      ) : null}
      {tab === "view" && parsed.data != null && kind === "monthly" ? (
        <MonthlyPackView data={parsed.data as MonthlyPack} lang={lang} />
      ) : null}
      {tab === "view" && parsed.data != null && kind === "input" ? (
        <InputPackView data={parsed.data as InputPack} lang={lang} />
      ) : null}
      {tab === "view" && parsed.data != null && kind === "journal" ? (
        <JournalPackView data={parsed.data as JournalPack} lang={lang} />
      ) : null}
      {tab === "view" && parsed.data != null && kind === "generic" ? (
        <GenericPackView data={parsed.data} lang={lang} />
      ) : null}
    </div>
  );
}

/* ---------- cash_and_invoices ---------- */

type CashPack = {
  meta?: { as_of?: string; scenario?: string; currency?: string; note?: string };
  balance_history?: { date: string; balance: number }[];
  open_invoices?: {
    id: string;
    type: string;
    counterparty: string;
    description: string;
    issue_date: string;
    due_date: string;
    amount_incl_vat: number;
    status: string;
  }[];
  projection_from_open_invoices?: {
    week: number;
    week_end: string;
    sales_inflow: number;
    purchase_outflow: number;
    projected_balance: number;
  }[];
};

function CashPackView({ data, lang }: { data: CashPack; lang: Lang }) {
  const hist = data.balance_history || [];
  const inv = data.open_invoices || [];
  const proj = data.projection_from_open_invoices || [];
  const lastCash = hist.length ? hist[hist.length - 1].balance : 0;
  const firstCash = hist.length ? hist[0].balance : 0;
  const sales = inv.filter((i) => i.type === "sales");
  const purch = inv.filter((i) => i.type === "purchase");
  const salesSum = sales.reduce((s, i) => s + i.amount_incl_vat, 0);
  const purchSum = purch.reduce((s, i) => s + i.amount_incl_vat, 0);
  const overdue = inv.filter((i) => i.status === "overdue").length;
  const minProj = proj.length ? Math.min(...proj.map((p) => p.projected_balance)) : null;

  return (
    <div className="pack-view">
      <div className="summary-cards">
        <SummaryCard label={t("lastCash", lang)} value={fmtEur(lastCash, lang)} />
        <SummaryCard
          label={t("cashChange", lang)}
          value={fmtEur(lastCash - firstCash, lang)}
          tone={lastCash - firstCash >= 0 ? "ok" : "warn"}
        />
        <SummaryCard label={t("openInvoices", lang)} value={String(inv.length)} />
        <SummaryCard
          label={t("salesOpen", lang)}
          value={fmtEur(salesSum, lang)}
          hint={`${sales.length}`}
        />
        <SummaryCard
          label={t("purchasesOpen", lang)}
          value={fmtEur(purchSum, lang)}
          hint={`${purch.length}`}
        />
        <SummaryCard
          label={t("overdue", lang)}
          value={String(overdue)}
          tone={overdue ? "warn" : "ok"}
        />
        {minProj != null && (
          <SummaryCard
            label={t("minProjection", lang)}
            value={fmtEur(minProj, lang)}
            tone={minProj < 0 ? "danger" : "ok"}
          />
        )}
      </div>

      {data.meta?.note && <p className="muted pack-note">{data.meta.note}</p>}

      {hist.length > 0 && (
        <section className="pack-section">
          <h4>{t("cashHistory", lang)}</h4>
          <BalanceHistoryChart data={hist} lang={lang} />
        </section>
      )}

      {proj.length > 0 && (
        <section className="pack-section">
          <h4>{t("cashProjection", lang)}</h4>
          <ProjectionChart data={proj} lang={lang} />
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("week", lang)}</th>
                  <th>{t("weekEnd", lang)}</th>
                  <th>{t("salesInflow", lang)}</th>
                  <th>{t("purchaseOutflow", lang)}</th>
                  <th>{t("projectedBalance", lang)}</th>
                </tr>
              </thead>
              <tbody>
                {proj.map((w) => (
                  <tr key={w.week} className={w.projected_balance < 0 ? "row-danger" : undefined}>
                    <td>{w.week}</td>
                    <td>{w.week_end}</td>
                    <td className="num">{fmtEur(w.sales_inflow, lang)}</td>
                    <td className="num">{fmtEur(w.purchase_outflow, lang)}</td>
                    <td className="num">{fmtEur(w.projected_balance, lang)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {inv.length > 0 && (
        <section className="pack-section">
          <h4>{t("openInvoices", lang)}</h4>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>{t("type", lang)}</th>
                  <th>{t("counterparty", lang)}</th>
                  <th>{t("description", lang)}</th>
                  <th>{t("dueDate", lang)}</th>
                  <th>{t("amount", lang)}</th>
                  <th>{t("status", lang)}</th>
                </tr>
              </thead>
              <tbody>
                {inv.map((i) => (
                  <tr key={i.id} className={i.status === "overdue" ? "row-warn" : undefined}>
                    <td>{i.id}</td>
                    <td>{i.type === "sales" ? t("sales", lang) : t("purchase", lang)}</td>
                    <td>{i.counterparty}</td>
                    <td>{i.description}</td>
                    <td>{i.due_date}</td>
                    <td className="num">{fmtEur(i.amount_incl_vat, lang)}</td>
                    <td>{i.status === "overdue" ? t("overdue", lang) : t("openStatus", lang)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

/* ---------- monthly_reports ---------- */

type MonthlyPack = {
  meta?: { note?: string; scenario?: string };
  months?: {
    month: string;
    income_statement: Record<string, number>;
    balance_sheet: {
      assets: Record<string, number>;
      equity_and_liabilities: Record<string, number>;
    };
  }[];
};

function MonthlyPackView({ data, lang }: { data: MonthlyPack; lang: Lang }) {
  const months = data.months || [];
  const chartRows = months.map((m) => ({
    month: m.month,
    revenue: m.income_statement.revenue,
    net: m.income_statement.net_result,
    cash: m.balance_sheet.assets.cash,
  }));
  const last = months[months.length - 1];

  return (
    <div className="pack-view">
      {last && (
        <div className="summary-cards">
          <SummaryCard label={t("months", lang)} value={String(months.length)} />
          <SummaryCard label={t("lastRevenue", lang)} value={fmtEur(last.income_statement.revenue, lang)} />
          <SummaryCard
            label={t("lastNet", lang)}
            value={fmtEur(last.income_statement.net_result, lang)}
            tone={last.income_statement.net_result >= 0 ? "ok" : "danger"}
          />
          <SummaryCard label={t("lastCash", lang)} value={fmtEur(last.balance_sheet.assets.cash, lang)} />
        </div>
      )}

      {chartRows.length > 0 && (
        <section className="pack-section">
          <h4>{t("revenueAndCash", lang)}</h4>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartRows}>
                <CartesianGrid stroke="rgba(232,242,239,0.08)" vertical={false} />
                <XAxis dataKey="month" tick={{ fill: "#a7c4bf", fontSize: 11 }} minTickGap={20} />
                <YAxis tick={{ fill: "#a7c4bf", fontSize: 12 }} tickFormatter={(v) => `${Math.round(Number(v) / 1000)}k`} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => fmtEur(Number(v), lang)} />
                <Legend />
                <Line type="monotone" dataKey="revenue" stroke="#d4a017" strokeWidth={2} name={t("revenue", lang)} dot={false} />
                <Line type="monotone" dataKey="cash" stroke="#3dbf8f" strokeWidth={2} name={t("cash", lang)} dot={false} />
                <Line type="monotone" dataKey="net" stroke="#e07060" strokeWidth={1.5} strokeDasharray="4 3" name={t("netResult", lang)} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {months.length > 0 && (
        <section className="pack-section">
          <h4>{t("incomeStatement", lang)}</h4>
          <div className="table-wrap">
            <table className="data-table compact">
              <thead>
                <tr>
                  <th>{t("month", lang)}</th>
                  <th>{t("revenue", lang)}</th>
                  <th>{t("materialsServices", lang)}</th>
                  <th>{t("personnel", lang)}</th>
                  <th>{t("operatingProfit", lang)}</th>
                  <th>{t("netResult", lang)}</th>
                </tr>
              </thead>
              <tbody>
                {months.map((m) => (
                  <tr key={m.month}>
                    <td>{m.month}</td>
                    <td className="num">{fmtEur(m.income_statement.revenue, lang)}</td>
                    <td className="num">{fmtEur(m.income_statement.materials_and_services, lang)}</td>
                    <td className="num">{fmtEur(m.income_statement.personnel_costs, lang)}</td>
                    <td className="num">{fmtEur(m.income_statement.operating_profit, lang)}</td>
                    <td className={`num ${m.income_statement.net_result < 0 ? "neg" : ""}`}>
                      {fmtEur(m.income_statement.net_result, lang)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {months.length > 0 && (
        <section className="pack-section">
          <h4>{t("balanceSheet", lang)}</h4>
          <div className="table-wrap">
            <table className="data-table compact">
              <thead>
                <tr>
                  <th>{t("month", lang)}</th>
                  <th>{t("cash", lang)}</th>
                  <th>{t("receivables", lang)}</th>
                  <th>{t("payables", lang)}</th>
                  <th>{t("equity", lang)}</th>
                  <th>{t("totalAssets", lang)}</th>
                </tr>
              </thead>
              <tbody>
                {months.map((m) => (
                  <tr key={m.month}>
                    <td>{m.month}</td>
                    <td className="num">{fmtEur(m.balance_sheet.assets.cash, lang)}</td>
                    <td className="num">{fmtEur(m.balance_sheet.assets.receivables, lang)}</td>
                    <td className="num">{fmtEur(m.balance_sheet.equity_and_liabilities.payables, lang)}</td>
                    <td className="num">{fmtEur(m.balance_sheet.equity_and_liabilities.equity, lang)}</td>
                    <td className="num">{fmtEur(m.balance_sheet.assets.total_assets, lang)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

/* ---------- input.json ---------- */

type InputPack = {
  meta?: { note?: string };
  scenario_description?: { fi?: string; en?: string };
  options?: Record<string, unknown>;
  parameters_from_language_model?: Record<string, unknown>;
};

function InputPackView({ data, lang }: { data: InputPack; lang: Lang }) {
  const desc = data.scenario_description;
  const opts = data.options || {};
  const params = data.parameters_from_language_model || {};
  const shares = (params.cost_shares_of_revenue || {}) as Record<string, number>;
  const shareRows = Object.entries(shares).map(([k, v]) => ({ name: k, value: Number(v) }));

  return (
    <div className="pack-view">
      {(desc?.fi || desc?.en) && (
        <section className="pack-section">
          <h4>{t("description", lang)}</h4>
          <div className="bilingual-block">
            {desc?.fi && (
              <div>
                <span className="lang-chip">FI</span>
                <p>{desc.fi}</p>
              </div>
            )}
            {desc?.en && (
              <div>
                <span className="lang-chip">EN</span>
                <p>{desc.en}</p>
              </div>
            )}
          </div>
        </section>
      )}

      <div className="summary-cards">
        {"monthly_revenue_start_eur" in params && (
          <SummaryCard
            label={t("revenueStart", lang)}
            value={fmtEur(Number(params.monthly_revenue_start_eur), lang)}
          />
        )}
        {"monthly_revenue_growth" in params && (
          <SummaryCard label={t("growth", lang)} value={fmtPct(Number(params.monthly_revenue_growth), lang)} />
        )}
        {"target_cash_at_end_eur" in params && (
          <SummaryCard
            label={t("targetCash", lang)}
            value={fmtEur(Number(params.target_cash_at_end_eur), lang)}
          />
        )}
        {"special_investment_eur" in params && (
          <SummaryCard
            label={t("investment", lang)}
            value={fmtEur(Number(params.special_investment_eur), lang)}
          />
        )}
        {"days_sales_outstanding" in params && (
          <SummaryCard label="DSO" value={`${fmtNum(Number(params.days_sales_outstanding), lang, 0)} ${t("days", lang)}`} />
        )}
        {"days_payables_outstanding" in params && (
          <SummaryCard label="DPO" value={`${fmtNum(Number(params.days_payables_outstanding), lang, 0)} ${t("days", lang)}`} />
        )}
      </div>

      {Object.keys(opts).length > 0 && (
        <section className="pack-section">
          <h4>{t("options", lang)}</h4>
          <div className="table-wrap">
            <table className="data-table">
              <tbody>
                {Object.entries(opts).map(([k, v]) => (
                  <tr key={k}>
                    <td className="key-cell">{k}</td>
                    <td>{String(v ?? "")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {shareRows.length > 0 && (
        <section className="pack-section">
          <h4>{t("costShares", lang)}</h4>
          <div className="chart-wrap chart-wrap-sm">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={shareRows}>
                <CartesianGrid stroke="rgba(232,242,239,0.08)" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: "#a7c4bf", fontSize: 12 }} />
                <YAxis tick={{ fill: "#a7c4bf", fontSize: 12 }} tickFormatter={(v) => `${Math.round(Number(v) * 100)}%`} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => fmtPct(Number(v), lang)} />
                <Bar dataKey="value" fill="#d4a017" name={t("costShares", lang)} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {params.notes != null && String(params.notes) && (
        <p className="muted pack-note">
          <strong>{t("paramNotes", lang)}:</strong> {String(params.notes)}
        </p>
      )}
    </div>
  );
}

/* ---------- journal_entries ---------- */

type JournalPack = {
  meta?: { note?: string; as_of?: string };
  chart_note_fi?: string;
  chart_note_en?: string;
  entries?: {
    id: string;
    date: string;
    description_fi: string;
    description_en: string;
    source: string;
    lines: {
      account: string;
      account_name_fi: string;
      account_name_en: string;
      debit: number;
      credit: number;
    }[];
  }[];
};

function JournalPackView({ data, lang }: { data: JournalPack; lang: Lang }) {
  const entries = data.entries || [];
  const [openId, setOpenId] = useState<string | null>(entries[0]?.id ?? null);
  const totalDebit = entries.reduce(
    (s, e) => s + e.lines.reduce((a, l) => a + l.debit, 0),
    0,
  );

  return (
    <div className="pack-view">
      <div className="summary-cards">
        <SummaryCard label={t("journalEntries", lang)} value={String(entries.length)} />
        <SummaryCard label={t("totalDebit", lang)} value={fmtEur(totalDebit, lang)} />
      </div>
      <p className="muted pack-note">{lang === "fi" ? data.chart_note_fi : data.chart_note_en}</p>

      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>{t("date", lang)}</th>
              <th>{t("description", lang)}</th>
              <th>{t("source", lang)}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <Fragment key={e.id}>
                <tr>
                  <td>{e.id}</td>
                  <td>{e.date}</td>
                  <td>{lang === "fi" ? e.description_fi : e.description_en}</td>
                  <td>{e.source}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-ghost btn-tiny"
                      onClick={() => setOpenId(openId === e.id ? null : e.id)}
                    >
                      {openId === e.id ? t("hideLines", lang) : t("showLines", lang)}
                    </button>
                  </td>
                </tr>
                {openId === e.id && (
                  <tr className="nested-row">
                    <td colSpan={5}>
                      <table className="data-table compact nested-table">
                        <thead>
                          <tr>
                            <th>{t("account", lang)}</th>
                            <th>{t("accountName", lang)}</th>
                            <th>{t("debit", lang)}</th>
                            <th>{t("credit", lang)}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {e.lines.map((l, idx) => (
                            <tr key={`${e.id}-${l.account}-${idx}`}>
                              <td>{l.account}</td>
                              <td>{lang === "fi" ? l.account_name_fi : l.account_name_en}</td>
                              <td className="num">{l.debit ? fmtEur(l.debit, lang) : "—"}</td>
                              <td className="num">{l.credit ? fmtEur(l.credit, lang) : "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ---------- generic ---------- */

function GenericPackView({ data, lang }: { data: unknown; lang: Lang }) {
  if (Array.isArray(data)) {
    return (
      <div className="pack-view">
        <p className="muted">
          {t("arrayItems", lang)}: {data.length}
        </p>
        <pre className="json-view">{JSON.stringify(data.slice(0, 20), null, 2)}</pre>
      </div>
    );
  }
  if (data && typeof data === "object") {
    const entries = Object.entries(data as Record<string, unknown>);
    return (
      <div className="pack-view">
        <div className="summary-cards">
          {entries.slice(0, 8).map(([k, v]) => (
            <SummaryCard
              key={k}
              label={k}
              value={
                Array.isArray(v)
                  ? `${v.length} ${t("items", lang)}`
                  : v && typeof v === "object"
                    ? t("object", lang)
                    : String(v ?? "—")
              }
            />
          ))}
        </div>
        <p className="muted">{t("useJsonTab", lang)}</p>
      </div>
    );
  }
  return <p className="muted">{String(data)}</p>;
}

function SummaryCard({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "ok" | "warn" | "danger";
}) {
  return (
    <div className={`summary-card ${tone ? `tone-${tone}` : ""}`}>
      <div className="summary-label">{label}</div>
      <div className="summary-value">
        {value}
        {hint != null && <span className="summary-hint"> · {hint}</span>}
      </div>
    </div>
  );
}

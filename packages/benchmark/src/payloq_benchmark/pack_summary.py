"""Build compact figure packs for reading / MoM / interpretation probes."""

from __future__ import annotations

from typing import Any

from payloq_schemas.models import ScenarioPack


def build_pack_summary(pack: ScenarioPack) -> dict[str, Any]:
    """
    Compact, code-owned figures for probes and interpretation.

    Models must read these numbers — they must not invent causes beyond what
    the figures support.
    """
    months = pack.monthly_reports.months
    last = months[-1]
    prev = months[-2] if len(months) >= 2 else None
    is_ = last.income_statement
    cash = pack.cash_and_invoices

    revenue_last = is_.revenue
    revenue_prev = prev.income_statement.revenue if prev else None
    mom_revenue_change = None
    mom_revenue_pct = None
    if revenue_prev is not None:
        mom_revenue_change = round(revenue_last - revenue_prev, 2)
        if abs(revenue_prev) > 1e-9:
            mom_revenue_pct = round(mom_revenue_change / revenue_prev, 6)

    cash_end = last.balance_sheet.assets.cash
    first_neg = None
    for w in cash.projection_from_open_invoices:
        if w.projected_balance < 0:
            first_neg = w.week
            break

    open_sales = sum(i.amount_incl_vat for i in cash.open_invoices if i.type == "sales")
    open_purch = sum(i.amount_incl_vat for i in cash.open_invoices if i.type == "purchase")

    return {
        "scenario_id": pack.input.options.scenario_id or pack.input.meta.scenario,
        "months": len(months),
        "last_month": last.month,
        "prev_month": prev.month if prev else None,
        "revenue_last": revenue_last,
        "revenue_prev": revenue_prev,
        "mom_revenue_change": mom_revenue_change,
        "mom_revenue_pct": mom_revenue_pct,
        "net_result_last": is_.net_result,
        "cash_end": cash_end,
        "receivables": last.balance_sheet.assets.receivables,
        "payables": last.balance_sheet.equity_and_liabilities.payables,
        "open_sales_sum": round(open_sales, 2),
        "open_purchase_sum": round(open_purch, 2),
        "first_negative_projection_week": first_neg,
        "projection_week_1_balance": cash.projection_from_open_invoices[0].projected_balance
        if cash.projection_from_open_invoices
        else None,
        "projection_week_3_balance": next(
            (w.projected_balance for w in cash.projection_from_open_invoices if w.week == 3),
            None,
        ),
        "balance_history_last": cash.balance_history[-1].balance if cash.balance_history else None,
        "allowed_facts": [
            "All figures above are produced by code from parameters.",
            "Projection excludes payroll/tax/recurring costs; overdue sales assumed paid in week 1.",
            "Do not invent external causes (customers leaving, bank freezes, fraud, etc.).",
        ],
    }

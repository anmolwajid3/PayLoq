"""Automated consistency checks (code calculates)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from payloq_schemas.constants import MONEY_TOLERANCE_EUR
from payloq_schemas.models import CashAndInvoices, GeneratorInput, MonthlyReports, ScenarioPack


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: str = "error"


@dataclass
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(self, code: str, message: str, *, severity: str = "error") -> None:
        self.issues.append(ValidationIssue(code=code, message=message, severity=severity))
        if severity == "error":
            self.ok = False


def validate_pack(pack: ScenarioPack) -> ValidationResult:
    result = ValidationResult(ok=True)
    _check_monthly(pack.monthly_reports, result)
    _check_cash(pack.cash_and_invoices, pack.monthly_reports, result)
    _check_behaviour(pack, result)
    return result


def validate_pack_dir(path: Path) -> ValidationResult:
    path = Path(path)
    inp = GeneratorInput.model_validate(json.loads((path / "input.json").read_text(encoding="utf-8")))
    monthly = MonthlyReports.model_validate(
        json.loads((path / "monthly_reports.json").read_text(encoding="utf-8"))
    )
    cash = CashAndInvoices.model_validate(
        json.loads((path / "cash_and_invoices.json").read_text(encoding="utf-8"))
    )
    return validate_pack(ScenarioPack(input=inp, monthly_reports=monthly, cash_and_invoices=cash))


def _near(a: float, b: float, tol: float = MONEY_TOLERANCE_EUR) -> bool:
    return abs(a - b) <= tol


def _check_monthly(monthly: MonthlyReports, result: ValidationResult) -> None:
    if not monthly.months:
        result.add("months_empty", "monthly_reports.months is empty")
        return

    prev_equity: float | None = None
    for m in monthly.months:
        is_ = m.income_statement
        bs = m.balance_sheet
        a = bs.assets
        e = bs.equity_and_liabilities

        # P&L arithmetic
        expected_op = (
            is_.revenue
            - is_.materials_and_services
            - is_.personnel_costs
            - is_.other_operating_costs
            - is_.depreciation
        )
        if not _near(is_.operating_profit, expected_op, tol=2.0):
            result.add(
                "pnl_operating_profit",
                f"{m.month}: operating_profit {is_.operating_profit} != {expected_op}",
            )
        if not _near(is_.profit_before_tax, is_.operating_profit - is_.interest_expense, tol=2.0):
            result.add("pnl_pbt", f"{m.month}: profit_before_tax inconsistent")
        if not _near(is_.net_result, is_.profit_before_tax - is_.income_tax, tol=2.0):
            result.add("pnl_net", f"{m.month}: net_result inconsistent")

        # Asset / liability totals
        assets_sum = a.fixed_assets + a.inventory + a.receivables + a.cash
        if not _near(a.total_assets, assets_sum):
            result.add("bs_assets_sum", f"{m.month}: total_assets != sum of asset lines")
        el_sum = e.equity + e.loans + e.payables + e.other_current_liabilities
        if not _near(e.total_equity_and_liabilities, el_sum):
            result.add("bs_el_sum", f"{m.month}: total_equity_and_liabilities != sum of lines")
        if not _near(a.total_assets, e.total_equity_and_liabilities):
            result.add(
                "bs_balance",
                f"{m.month}: assets {a.total_assets} != equity+liabilities {e.total_equity_and_liabilities}",
            )

        # Equity continuity: equity_t ≈ equity_{t-1} + net_result_t
        if prev_equity is not None:
            expected_eq = prev_equity + is_.net_result
            if not _near(e.equity, expected_eq, tol=2.0):
                result.add(
                    "equity_continuity",
                    f"{m.month}: equity {e.equity} != prev+net {expected_eq}",
                    severity="warning",
                )
        prev_equity = e.equity


def _check_cash(
    cash: CashAndInvoices,
    monthly: MonthlyReports,
    result: ValidationResult,
) -> None:
    if len(cash.balance_history) != 26:
        result.add(
            "history_len",
            f"balance_history length {len(cash.balance_history)} != 26",
            severity="warning",
        )

    last_cash = monthly.months[-1].balance_sheet.assets.cash
    hist_last = cash.balance_history[-1].balance
    if not _near(last_cash, hist_last):
        result.add(
            "cash_vs_history",
            f"last month cash {last_cash} != last balance history {hist_last}",
        )

    receivables = monthly.months[-1].balance_sheet.assets.receivables
    payables = monthly.months[-1].balance_sheet.equity_and_liabilities.payables
    sales = sum(i.amount_incl_vat for i in cash.open_invoices if i.type == "sales")
    purch = sum(i.amount_incl_vat for i in cash.open_invoices if i.type == "purchase")
    if not _near(sales, receivables):
        result.add("ar_vs_sales", f"Σ open sales {sales} != receivables {receivables}")
    if not _near(purch, payables):
        result.add("ap_vs_purchases", f"Σ open purchases {purch} != payables {payables}")

    if len(cash.projection_from_open_invoices) != 8:
        result.add(
            "projection_len",
            f"projection length {len(cash.projection_from_open_invoices)} != 8",
            severity="warning",
        )

    # Recompute projection from invoices
    if cash.meta.as_of and cash.projection_from_open_invoices:
        from datetime import date

        as_of = date.fromisoformat(cash.meta.as_of)
        bal = last_cash
        for i, week in enumerate(cash.projection_from_open_invoices):
            # Soft check: cumulative arithmetic
            expected = bal + week.sales_inflow - week.purchase_outflow
            if not _near(week.projected_balance, expected):
                result.add(
                    "projection_math",
                    f"week {week.week}: projected_balance {week.projected_balance} != {expected}",
                )
            bal = week.projected_balance
            _ = as_of  # reserved for due-date bucketing audits
            _ = i


def _check_behaviour(pack: ScenarioPack, result: ValidationResult) -> None:
    """Soft behavioural checks for the three ready-made profiles."""
    sid = (
        pack.input.options.scenario_id
        or pack.input.meta.scenario
        or pack.monthly_reports.meta.scenario
        or ""
    ).lower()
    months = pack.monthly_reports.months
    nets = [m.income_statement.net_result for m in months]
    cash_end = months[-1].balance_sheet.assets.cash
    proj = pack.cash_and_invoices.projection_from_open_invoices

    if sid == "good":
        if sum(nets) <= 0:
            result.add("behaviour_good_profit", "good scenario should be profitable overall", severity="warning")
        if any(w.projected_balance < 0 for w in proj):
            result.add("behaviour_good_cash", "good projection should stay non-negative", severity="warning")
    elif sid == "weak":
        if sum(nets) >= 0:
            result.add("behaviour_weak_loss", "weak scenario should show overall losses", severity="warning")
        if cash_end > months[0].balance_sheet.assets.cash:
            result.add("behaviour_weak_cash", "weak scenario cash should shrink", severity="warning")
    elif sid == "cash_critical":
        # Near-term negative cash around week 3
        neg_weeks = [w.week for w in proj if w.projected_balance < 0]
        if not neg_weeks:
            result.add(
                "behaviour_cash_critical",
                "cash_critical projection should go negative near-term",
                severity="warning",
            )
        elif min(neg_weeks) > 4:
            result.add(
                "behaviour_cash_critical_timing",
                f"cash_critical first negative week is {min(neg_weeks)} (expected ~3)",
                severity="warning",
            )
        if sum(nets) <= 0:
            result.add(
                "behaviour_cash_critical_pnl",
                "cash_critical should remain overall profitable",
                severity="warning",
            )

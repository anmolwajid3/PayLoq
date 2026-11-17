"""Automated consistency checks (code calculates). SRS VR-01..13, VR-20..22."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from payloq_schemas.constants import (
    FORBIDDEN_TEXT_WORDS,
    MONEY_TOLERANCE_EUR,
    PROJECTION_HISTORY_SCALE_RATIO,
    VAT_RATE_FI,
)
from payloq_schemas.models import CashAndInvoices, GeneratorInput, MonthlyReports, ScenarioPack
from payloq_schemas.text_rules import descriptive_text_has_numbers


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: str = "error"
    rule_id: str | None = None
    numbers: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "rule_id": self.rule_id or self.code,
            "message": self.message,
            "severity": self.severity,
            "numbers": self.numbers,
        }


@dataclass
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(
        self,
        code: str,
        message: str,
        *,
        severity: str = "error",
        rule_id: str | None = None,
        numbers: dict[str, Any] | None = None,
    ) -> None:
        self.issues.append(
            ValidationIssue(
                code=code,
                message=message,
                severity=severity,
                rule_id=rule_id or code,
                numbers=numbers or {},
            )
        )
        if severity == "error":
            self.ok = False

    def failing_rule_ids(self) -> list[str]:
        return [
            (i.rule_id or i.code)
            for i in self.issues
            if i.severity == "error"
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "validation_result": "all checks PASS" if self.ok else "FAIL",
            "failing_rules": self.failing_rule_ids(),
            "issues": [i.as_dict() for i in self.issues],
        }


def validate_pack(
    pack: ScenarioPack,
    *,
    answer_key: dict[str, Any] | None = None,
) -> ValidationResult:
    result = ValidationResult(ok=True)
    _check_monthly(pack.monthly_reports, result)
    _check_cash(pack.cash_and_invoices, pack.monthly_reports, result)
    _check_invoices(pack.cash_and_invoices, result)
    _check_texts(pack, result)
    _check_behaviour(pack, result)
    if answer_key is not None:
        _check_answer_key(pack, answer_key, result)
    return result


def validate_pack_dir(path: Path, *, answer_key_path: Path | None = None) -> ValidationResult:
    path = Path(path)
    inp = GeneratorInput.model_validate(json.loads((path / "input.json").read_text(encoding="utf-8")))
    monthly = MonthlyReports.model_validate(
        json.loads((path / "monthly_reports.json").read_text(encoding="utf-8"))
    )
    cash = CashAndInvoices.model_validate(
        json.loads((path / "cash_and_invoices.json").read_text(encoding="utf-8"))
    )
    answer_key = None
    key_file = answer_key_path or (path / "answer_key.json")
    if key_file.exists():
        answer_key = json.loads(key_file.read_text(encoding="utf-8"))
    return validate_pack(
        ScenarioPack(input=inp, monthly_reports=monthly, cash_and_invoices=cash),
        answer_key=answer_key,
    )


def _near(a: float, b: float, tol: float = MONEY_TOLERANCE_EUR) -> bool:
    return abs(a - b) <= tol


def _add_one_month(yyyy_mm: str) -> str:
    y, m = map(int, yyyy_mm.split("-"))
    m += 1
    if m > 12:
        y += 1
        m = 1
    return f"{y:04d}-{m:02d}"


def _check_monthly(monthly: MonthlyReports, result: ValidationResult) -> None:
    if not monthly.months:
        result.add("months_empty", "monthly_reports.months is empty", rule_id="VR-01")
        return

    # VR-01: consecutive months
    for i in range(1, len(monthly.months)):
        prev = monthly.months[i - 1].month
        cur = monthly.months[i].month
        expected = _add_one_month(prev)
        if cur != expected:
            result.add(
                "months_sequence",
                f"Month gap/repeat: {prev} followed by {cur} (expected {expected})",
                rule_id="VR-01",
                numbers={"previous": prev, "current": cur, "expected": expected},
            )

    prev_equity: float | None = None
    for m in monthly.months:
        is_ = m.income_statement
        bs = m.balance_sheet
        a = bs.assets
        e = bs.equity_and_liabilities

        # VR-02: P&L arithmetic (map cost_of_sales ≈ materials_and_services;
        # operating_costs ≈ personnel + other + depreciation + interest for PBT path)
        expected_op = (
            is_.revenue
            - is_.materials_and_services
            - is_.personnel_costs
            - is_.other_operating_costs
            - is_.depreciation
        )
        if not _near(is_.operating_profit, expected_op):
            result.add(
                "pnl_operating_profit",
                f"{m.month}: operating_profit {is_.operating_profit} != {expected_op}",
                rule_id="VR-02",
                numbers={"month": m.month, "got": is_.operating_profit, "expected": expected_op},
            )
        expected_pbt = is_.operating_profit - is_.interest_expense
        if not _near(is_.profit_before_tax, expected_pbt):
            result.add(
                "pnl_pbt",
                f"{m.month}: profit_before_tax inconsistent",
                rule_id="VR-02",
                numbers={"month": m.month, "got": is_.profit_before_tax, "expected": expected_pbt},
            )
        if not _near(is_.net_result, is_.profit_before_tax - is_.income_tax):
            result.add(
                "pnl_net",
                f"{m.month}: net_result inconsistent",
                rule_id="VR-02",
                numbers={"month": m.month},
            )

        # VR-04: Balance sheet balances
        assets_sum = a.fixed_assets + a.inventory + a.receivables + a.cash
        if not _near(a.total_assets, assets_sum):
            result.add(
                "bs_assets_sum",
                f"{m.month}: total_assets != sum of asset lines",
                rule_id="VR-04",
                numbers={"month": m.month, "total": a.total_assets, "sum": assets_sum},
            )
        el_sum = e.equity + e.loans + e.payables + e.other_current_liabilities
        if not _near(e.total_equity_and_liabilities, el_sum):
            result.add(
                "bs_el_sum",
                f"{m.month}: total_equity_and_liabilities != sum of lines",
                rule_id="VR-04",
                numbers={"month": m.month},
            )
        if not _near(a.total_assets, e.total_equity_and_liabilities):
            result.add(
                "bs_balance",
                f"{m.month}: assets {a.total_assets} != equity+liabilities "
                f"{e.total_equity_and_liabilities}",
                rule_id="VR-04",
                numbers={
                    "month": m.month,
                    "assets": a.total_assets,
                    "equity_liabilities": e.total_equity_and_liabilities,
                },
            )

        if prev_equity is not None:
            expected_eq = prev_equity + is_.net_result
            if not _near(e.equity, expected_eq, tol=2.0):
                result.add(
                    "equity_continuity",
                    f"{m.month}: equity {e.equity} != prev+net {expected_eq}",
                    severity="warning",
                    rule_id="VR-04",
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
            rule_id="VR-07",
        )

    last_cash = monthly.months[-1].balance_sheet.assets.cash
    hist_last = cash.balance_history[-1].balance
    if not _near(last_cash, hist_last):
        result.add(
            "cash_vs_history",
            f"last month cash {last_cash} != last balance history {hist_last}",
            rule_id="VR-07",
            numbers={"last_month_cash": last_cash, "history_last": hist_last},
        )

    receivables = monthly.months[-1].balance_sheet.assets.receivables
    payables = monthly.months[-1].balance_sheet.equity_and_liabilities.payables
    sales = sum(i.amount_incl_vat for i in cash.open_invoices if i.type == "sales")
    purch = sum(i.amount_incl_vat for i in cash.open_invoices if i.type == "purchase")
    if not _near(sales, receivables):
        result.add(
            "ar_vs_sales",
            f"Σ open sales {sales} != receivables {receivables}",
            rule_id="VR-05",
            numbers={"sales_sum": sales, "receivables": receivables},
        )
    if not _near(purch, payables):
        result.add(
            "ap_vs_purchases",
            f"Σ open purchases {purch} != payables {payables}",
            rule_id="VR-06",
            numbers={"purchases_sum": purch, "payables": payables},
        )

    n_inv = len(cash.open_invoices)
    if n_inv < 15 or n_inv > 25:
        result.add(
            "invoice_count",
            f"open invoice count {n_inv} not in 15..25",
            rule_id="FR-A-23",
            numbers={"count": n_inv},
        )

    if len(cash.projection_from_open_invoices) != 8:
        result.add(
            "projection_len",
            f"projection length {len(cash.projection_from_open_invoices)} != 8",
            severity="warning",
            rule_id="VR-08",
        )

    # VR-08: projection arithmetic from open invoices only (week deltas)
    if cash.meta.as_of and cash.projection_from_open_invoices:
        as_of = date.fromisoformat(cash.meta.as_of)
        bal = last_cash
        for week in cash.projection_from_open_invoices:
            expected = round(bal + week.sales_inflow - week.purchase_outflow, 2)
            if not _near(week.projected_balance, expected):
                result.add(
                    "projection_math",
                    f"week {week.week}: projected_balance {week.projected_balance} != {expected}",
                    rule_id="VR-08",
                    numbers={
                        "week": week.week,
                        "got": week.projected_balance,
                        "expected": expected,
                    },
                )
            bal = week.projected_balance

        # Re-bucket invoices and compare week inflows/outflows
        sales_b = [0.0] * 8
        purch_b = [0.0] * 8
        for inv in cash.open_invoices:
            due = date.fromisoformat(inv.due_date)
            if inv.type == "sales":
                if inv.status == "overdue" or due <= as_of:
                    sales_b[0] += inv.amount_incl_vat
                else:
                    delta = (due - as_of).days
                    w = int(math.ceil(delta / 7.0))
                    if 1 <= w <= 8:
                        sales_b[w - 1] += inv.amount_incl_vat
            else:
                if due <= as_of:
                    purch_b[0] += inv.amount_incl_vat
                else:
                    delta = (due - as_of).days
                    w = int(math.ceil(delta / 7.0))
                    if 1 <= w <= 8:
                        purch_b[w - 1] += inv.amount_incl_vat
        for i, week in enumerate(cash.projection_from_open_invoices):
            if not _near(week.sales_inflow, round(sales_b[i], 2), tol=1.0):
                result.add(
                    "projection_sales_bucket",
                    f"week {week.week}: sales_inflow not explained by open invoices alone",
                    rule_id="VR-08",
                    numbers={
                        "week": week.week,
                        "got": week.sales_inflow,
                        "from_invoices": round(sales_b[i], 2),
                    },
                )
            if not _near(week.purchase_outflow, round(purch_b[i], 2), tol=1.0):
                result.add(
                    "projection_purch_bucket",
                    f"week {week.week}: purchase_outflow not explained by open invoices alone",
                    rule_id="VR-08",
                    numbers={
                        "week": week.week,
                        "got": week.purchase_outflow,
                        "from_invoices": round(purch_b[i], 2),
                    },
                )

    # VR-08 related: warn when projection week moves wildly diverge from history scale
    # (e.g. history ±30–90k vs projection ±400k). Usually open-invoice stock vs
    # smoothed history — not a unit bug — but worth flagging for review.
    if len(cash.balance_history) >= 2 and cash.projection_from_open_invoices:
        hist_deltas = [
            abs(cash.balance_history[i].balance - cash.balance_history[i - 1].balance)
            for i in range(1, len(cash.balance_history))
        ]
        proj_deltas = [
            abs(w.sales_inflow) + abs(w.purchase_outflow)
            for w in cash.projection_from_open_invoices
        ]
        max_hist = max(hist_deltas) if hist_deltas else 0.0
        max_proj = max(proj_deltas) if proj_deltas else 0.0
        if max_hist > 1.0 and max_proj > PROJECTION_HISTORY_SCALE_RATIO * max_hist:
            result.add(
                "projection_history_scale",
                (
                    f"Projection weekly cash moves (max {max_proj:,.0f} €) diverge "
                    f">{PROJECTION_HISTORY_SCALE_RATIO:.0f}× from history week moves "
                    f"(max {max_hist:,.0f} €). Open-invoice stock may dwarf smoothed history."
                ),
                severity="warning",
                rule_id="VR-08",
                numbers={
                    "max_projection_week_move_eur": max_proj,
                    "max_history_week_move_eur": max_hist,
                    "ratio": round(max_proj / max_hist, 2) if max_hist else None,
                },
            )


def _check_invoices(cash: CashAndInvoices, result: ValidationResult) -> None:
    for inv in cash.open_invoices:
        # VR-12
        if not (inv.counterparty or "").strip():
            result.add(
                "empty_counterparty",
                f"Invoice {inv.id} has empty counterparty",
                rule_id="VR-12",
                numbers={"invoice_id": inv.id},
            )
        # VR-09
        try:
            issue = date.fromisoformat(inv.issue_date)
            due = date.fromisoformat(inv.due_date)
        except ValueError:
            result.add(
                "bad_invoice_date",
                f"Invoice {inv.id} has non-ISO date",
                rule_id="VR-09",
            )
            continue
        if due < issue:
            result.add(
                "due_before_issue",
                f"Invoice {inv.id}: due_date {inv.due_date} before issue_date {inv.issue_date}",
                rule_id="VR-09",
                numbers={"invoice_id": inv.id, "issue": inv.issue_date, "due": inv.due_date},
            )
        # VR-03 VAT
        net = inv.amount_net_eur
        vat = inv.vat_eur
        gross = inv.amount_incl_vat
        if net is None or vat is None:
            # Derive expected from gross
            expected_net = round(gross / (1.0 + VAT_RATE_FI), 2)
            expected_vat = round(gross - expected_net, 2)
            # If fields missing, treat as soft unless we require them
            result.add(
                "vat_fields_missing",
                f"Invoice {inv.id}: amount_net_eur/vat_eur missing "
                f"(expected net≈{expected_net}, vat≈{expected_vat})",
                severity="warning",
                rule_id="VR-03",
            )
        else:
            expected_gross = round(net * (1.0 + VAT_RATE_FI), 2)
            # Prefer cent check: gross ≈ net + vat and gross ≈ net * 1.255
            if not _near(gross, round(net + vat, 2)):
                result.add(
                    "vat_sum",
                    f"Invoice {inv.id}: net+vat {net + vat} != gross {gross}",
                    rule_id="VR-03",
                    numbers={"invoice_id": inv.id, "net": net, "vat": vat, "gross": gross},
                )
            if not _near(gross, expected_gross, tol=0.05):
                result.add(
                    "vat_rate",
                    f"Invoice {inv.id}: gross {gross} != net×1.255 {expected_gross}",
                    rule_id="VR-03",
                    numbers={
                        "invoice_id": inv.id,
                        "net": net,
                        "gross": gross,
                        "expected_gross": expected_gross,
                    },
                )


def _check_texts(pack: ScenarioPack, result: ValidationResult) -> None:
    for inv in pack.cash_and_invoices.open_invoices:
        for field_name, text in (
            ("counterparty", inv.counterparty),
            ("description", inv.description),
        ):
            # VR-13: no digits in descriptive texts (invoice id exempt)
            if descriptive_text_has_numbers(text):
                result.add(
                    "text_has_numbers",
                    f"Invoice {inv.id} {field_name} contains numbers: {text!r}",
                    rule_id="VR-13",
                    numbers={"invoice_id": inv.id, "field": field_name},
                )
            low = (text or "").lower()
            for word in FORBIDDEN_TEXT_WORDS:
                if word in low:
                    result.add(
                        "forbidden_word",
                        f"Invoice {inv.id} {field_name} contains forbidden word '{word}'",
                        rule_id="FR-A-33",
                        numbers={"invoice_id": inv.id, "word": word},
                    )


def _behaviour_sid(pack: ScenarioPack) -> str:
    """Preset id when labelled; else infer from note / params (custom pack labels)."""
    sid = (
        pack.input.options.scenario_id
        or pack.input.meta.scenario
        or pack.monthly_reports.meta.scenario
        or ""
    ).lower()
    presets = {
        "good",
        "weak",
        "cash_critical",
        "cash_turning_critical_later",
        "invoices_out_of_balance",
        "test_only_broken",
    }
    if sid in presets:
        return sid
    note = pack.input.meta.note or ""
    profile_from_note: str | None = None
    if "behavior_profile=" in note:
        profile_from_note = note.split("behavior_profile=")[-1].split("|")[0].strip().lower()
    # Fall back to param / NL heuristics for custom from_text packs.
    # Prefer cash-stress detection over a stale behavior_profile=good stamp when
    # the description/params clearly contradict a healthy pack (Run #9).
    cash = pack.input.parameters_from_language_model.target_cash_at_end_eur
    growth = pack.input.parameters_from_language_model.monthly_revenue_growth
    text = f"{pack.input.scenario_description.fi} {pack.input.scenario_description.en}"
    text_l = text.lower()
    try:
        from payloq_llm.nl_cash_intent import looks_cash_critical
    except ImportError:  # pragma: no cover
        looks_cash_critical = None  # type: ignore[assignment]
    cash_stressed = cash <= 60_000 or (
        looks_cash_critical is not None and looks_cash_critical(text)
    ) or any(
        k in text_l
        for k in (
            "kriittinen",
            "critical",
            "cash tight",
            "negatiiv",
            "covenant",
            "kovenantti",
            "winter cash",
            "ohut kassa",
        )
    )
    if growth < -0.005:
        return "weak"
    if cash_stressed:
        return "cash_critical"
    if profile_from_note in presets:
        return profile_from_note  # type: ignore[return-value]
    return sid or "custom"


def _check_behaviour(pack: ScenarioPack, result: ValidationResult) -> None:
    """Scenario-level rules VR-20..22."""
    sid = _behaviour_sid(pack)
    months = pack.monthly_reports.months
    nets = [m.income_statement.net_result for m in months]
    cash_end = months[-1].balance_sheet.assets.cash
    proj = pack.cash_and_invoices.projection_from_open_invoices
    hist = pack.cash_and_invoices.balance_history

    # VR-21: at least one month with ≥5% revenue change
    big_move = False
    for i in range(1, len(months)):
        prev = months[i - 1].income_statement.revenue
        cur = months[i].income_statement.revenue
        if prev and abs(cur - prev) / abs(prev) >= 0.05:
            big_move = True
            break
    if not big_move and sid not in {"invoices_out_of_balance", "test_only_broken"}:
        result.add(
            "revenue_volatility",
            "No month-to-month revenue change ≥ 5% (VR-21)",
            rule_id="VR-21",
            severity="error" if sid in {"good", "weak", "cash_critical", "cash_turning_critical_later"} else "warning",
        )

    if sid == "good":
        # VR-22 / Run #9: never apply good-profit to cash-stressed packs.
        # _behaviour_sid already prefers cash_critical when NL/params say so;
        # keep an extra guard if sid is the ready-made "good" preset only.
        if sum(nets) <= 0:
            result.add(
                "behaviour_good_profit",
                "good scenario should be profitable overall",
                rule_id="VR-20",
            )
        if any(w.projected_balance < 0 for w in proj) or any(p.balance < 0 for p in hist):
            result.add(
                "behaviour_good_cash",
                "good scenario cash should stay non-negative",
                rule_id="VR-20",
            )
    elif sid == "weak":
        if sum(nets) >= 0:
            result.add(
                "behaviour_weak_loss",
                "weak scenario should show overall losses",
                rule_id="VR-20",
            )
        if cash_end > months[0].balance_sheet.assets.cash:
            result.add(
                "behaviour_weak_cash",
                "weak scenario cash should shrink",
                rule_id="VR-20",
            )
    elif sid == "cash_critical":
        # VR-20 MUST: negative cash somewhere (projection and/or history).
        neg_proj = [w.week for w in proj if w.projected_balance < 0]
        neg_hist = [p.week for p in hist if p.balance < 0]
        if not neg_proj and not neg_hist:
            result.add(
                "behaviour_cash_critical",
                "cash_critical must show negative cash in ≥1 week (projection or history)",
                rule_id="VR-20",
            )
        elif neg_proj and min(neg_proj) > 4:
            result.add(
                "behaviour_cash_critical_timing",
                f"cash_critical first negative projection week is {min(neg_proj)} (expected ~3)",
                rule_id="VR-20",
                numbers={"first_negative_week": min(neg_proj)},
                severity="warning",
            )
        # VR-22: profitable + negative cash is allowed / expected — do NOT hard-fail
        # on unprofitable cash_critical. Demote former behaviour_cash_critical_pnl.
        if sum(nets) <= 0:
            result.add(
                "behaviour_cash_critical_pnl",
                "cash_critical is often profitable (VR-22), but negative P&L is allowed; "
                "VR-20 only requires negative cash somewhere",
                severity="warning",
                rule_id="VR-22",
            )
        if sum(nets) > 0 and (neg_proj or neg_hist):
            result.add(
                "profitable_with_negative_cash",
                "VR-22: profitable scenario with negative cash (expected for cash_critical)",
                severity="warning",
                rule_id="VR-22",
            )
    elif sid == "cash_turning_critical_later":
        neg_hist = [p.week for p in hist if p.balance < 0]
        if not neg_hist:
            result.add(
                "behaviour_later_critical",
                "cash_turning_critical_later should go negative in balance history (~week 20)",
                rule_id="VR-20",
            )
        else:
            first = min(neg_hist)
            if abs(first - 20) > 2:
                result.add(
                    "behaviour_later_critical_timing",
                    f"first negative history week {first} (expected ~20 ±2)",
                    rule_id="VR-20",
                    numbers={"first_negative_week": first},
                )


def _check_answer_key(
    pack: ScenarioPack,
    answer_key: dict[str, Any],
    result: ValidationResult,
) -> None:
    """VR-11: every number in the answer key must appear in the generated data."""
    findings = answer_key.get("key_findings") or []
    months = pack.monthly_reports.months
    proj = {w.week: w.projected_balance for w in pack.cash_and_invoices.projection_from_open_invoices}
    hist = {p.week: p.balance for p in pack.cash_and_invoices.balance_history}

    for finding in findings:
        fid = finding.get("id")
        val = finding.get("value")
        week = finding.get("week")
        if fid == "cash_end" and months and val is not None:
            if not _near(float(val), months[-1].balance_sheet.assets.cash):
                result.add(
                    "answer_key_cash_end",
                    f"answer_key cash_end {val} != data {months[-1].balance_sheet.assets.cash}",
                    rule_id="VR-11",
                    numbers={"key": val, "data": months[-1].balance_sheet.assets.cash},
                )
        if fid == "first_negative_projection_week" and val is not None:
            if int(val) not in proj or proj[int(val)] >= 0:
                result.add(
                    "answer_key_neg_week",
                    f"answer_key says negative in projection week {val} but data disagrees",
                    rule_id="VR-11",
                    numbers={"week": val, "balance": proj.get(int(val))},
                )
        if fid == "first_negative_history_week" and val is not None:
            if int(val) not in hist or hist[int(val)] >= 0:
                result.add(
                    "answer_key_neg_hist",
                    f"answer_key says negative in history week {val} but data disagrees",
                    rule_id="VR-11",
                    numbers={"week": val, "balance": hist.get(int(val))},
                )
        if week is not None and fid == "lowest_projection_balance" and val is not None:
            if int(week) in proj and not _near(float(val), proj[int(week)]):
                result.add(
                    "answer_key_lowest_proj",
                    f"answer_key lowest projection {val} != week {week} data {proj[int(week)]}",
                    rule_id="VR-11",
                )

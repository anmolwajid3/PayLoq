"""Params → monthly reports, cash history, open invoices, projection."""

from __future__ import annotations

import json
import math
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from payloq_schemas.constants import CORPORATE_TAX_RATE, VAT_RATE_FI
from payloq_schemas.models import (
    Assets,
    BalanceHistoryPoint,
    BalanceSheet,
    CashAndInvoices,
    EquityAndLiabilities,
    GeneratorInput,
    IncomeStatement,
    InvoiceDescriptiveTexts,
    MonthlyReport,
    MonthlyReports,
    OneOffCashEvent,
    OpenInvoice,
    ProjectionWeek,
    ScenarioMeta,
    ScenarioPack,
)

from payloq_generator.text_fi import (
    PURCHASE_COUNTERPARTIES_FI,
    PURCHASE_DESCRIPTIONS_FI,
    SALES_COUNTERPARTIES_FI,
    SALES_DESCRIPTIONS_FI,
    pick,
)
from payloq_generator.text_sanitize import sanitize_invoice_texts_for_pack


def _r(value: float) -> float:
    """Round money to cents (SRS DR-02)."""
    return float(round(value, 2))


def _vat_split(gross: float) -> tuple[float, float, float]:
    """Return (net, vat, gross) for a VAT-inclusive amount."""
    gross = _r(gross)
    net = _r(gross / (1.0 + VAT_RATE_FI))
    vat = _r(gross - net)
    return net, vat, gross


def _parse_month(yyyy_mm: str) -> date:
    y, m = map(int, yyyy_mm.split("-"))
    return date(y, m, 1)


def _add_months(d: date, n: int) -> date:
    y = d.year + (d.month - 1 + n) // 12
    m = (d.month - 1 + n) % 12 + 1
    return date(y, m, 1)


def _month_end(d: date) -> date:
    nxt = _add_months(d.replace(day=1), 1)
    return nxt - timedelta(days=1)


def _fmt_month(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


_PRESET_IDS = frozenset(
    {
        "good",
        "weak",
        "cash_critical",
        "cash_turning_critical_later",
        "invoices_out_of_balance",
        "test_only_broken",
    }
)


def _infer_profile(inp: GeneratorInput) -> str:
    """Behaviour profile used by the cash/invoice generators (not the pack filename)."""
    sid = (inp.options.scenario_id or inp.meta.scenario or "").strip().lower()
    if sid in _PRESET_IDS:
        return "invoices_out_of_balance" if sid == "test_only_broken" else sid
    g = inp.parameters_from_language_model.monthly_revenue_growth
    cash = inp.parameters_from_language_model.target_cash_at_end_eur
    text = f"{inp.scenario_description.fi} {inp.scenario_description.en}"
    text_l = text.lower()
    if g < -0.005:
        return "weak"
    try:
        from payloq_llm.nl_cash_intent import looks_cash_critical
    except ImportError:  # pragma: no cover — optional in minimal installs
        looks_cash_critical = None  # type: ignore[assignment]
    if cash <= 60_000 or (
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
    ):
        return "cash_critical"
    return "good"


def _slugify(text: str, *, fallback: str = "custom") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return (slug[:48] or fallback)


def _pack_label(inp: GeneratorInput, profile: str) -> str:
    """
    Filename / meta scenario label.

    Ready-made presets keep their ids. Custom --from-text packs use industry
    (or a short custom_* slug) so a boutique hotel is not mislabelled
    scenario_cash_critical.xlsx when behaviour is only cash-critical-like.
    """
    explicit = (inp.options.scenario_id or inp.meta.scenario or "").strip()
    if explicit:
        return _slugify(explicit, fallback=explicit.lower().replace(" ", "_"))
    industry = (inp.options.industry or "").strip()
    if industry:
        return _slugify(industry, fallback="custom")
    # Last resort: behaviour profile (documented in run_log as assigned_slug_source)
    return profile


def _collect_one_off_events(params) -> list[OneOffCashEvent]:
    """Merge special_investment_* into the structured one_off_events list."""
    events = list(params.one_off_events or [])
    invest = float(params.special_investment_eur or 0.0)
    if invest > 0:
        month_i = int(getattr(params, "special_investment_month", None) or 2)
        already = any(
            e.direction == "out"
            and abs(e.amount_eur - invest) < 0.02
            and e.month_index == month_i
            for e in events
        )
        if not already:
            events.append(
                OneOffCashEvent(
                    amount_eur=invest,
                    month_index=month_i,
                    direction="out",
                    label="special_investment",
                )
            )
    return events


def _events_for_month(events: list[OneOffCashEvent], month_index_1based: int) -> list[OneOffCashEvent]:
    return [e for e in events if e.month_index == month_index_1based]


def _ending_month(inp: GeneratorInput) -> date:
    """Last reporting month (YYYY-MM-01). Default Oct 2026 to align with examples."""
    if inp.options.as_of:
        as_of = date.fromisoformat(inp.options.as_of)
        return as_of.replace(day=1)
    return date(2026, 10, 1)


def _as_of_date(inp: GeneratorInput, last_month: date) -> date:
    if inp.options.as_of:
        return date.fromisoformat(inp.options.as_of)
    return _month_end(last_month)


def generate_pack(inp: GeneratorInput, *, seed: int = 42) -> ScenarioPack:
    """Generate a consistent scenario pack from structured parameters."""
    profile = _infer_profile(inp)
    params = inp.parameters_from_language_model
    n = inp.options.months
    last_month = _ending_month(inp)
    first_month = _add_months(last_month, -(n - 1))
    as_of = _as_of_date(inp, last_month)
    scenario_id = _pack_label(inp, profile)
    one_offs = _collect_one_off_events(params)

    partly_fixed = params.partly_fixed_costs or profile in {"weak", "cash_critical"}

    months, gen_meta = _generate_months(
        first_month=first_month,
        n=n,
        params=params,
        profile=profile,
        partly_fixed=partly_fixed,
        seed=seed,
        one_off_events=one_offs,
    )

    last_bs = months[-1].balance_sheet
    last_cash = last_bs.assets.cash
    receivables = last_bs.assets.receivables
    payables = last_bs.equity_and_liabilities.payables

    # cash_critical (VR-20): ensure the open-purchase cliff can breach cash even when
    # seasonality shrinks last-month working capital (e.g. hotel winter collapse).
    if profile == "cash_critical" and payables < last_cash * 1.15 + 5_000:
        needed = _r(last_cash * 1.25 + 10_000)
        bump = _r(needed - payables)
        payables = needed
        e = months[-1].balance_sheet.equity_and_liabilities
        a = months[-1].balance_sheet.assets
        e.payables = payables
        e.other_current_liabilities = _r(
            a.total_assets - e.equity - e.loans - e.payables
        )
        if e.other_current_liabilities < 0:
            a.cash = _r(a.cash + e.other_current_liabilities)
            last_cash = a.cash
            e.other_current_liabilities = 0.0
            a.total_assets = _r(a.fixed_assets + a.inventory + a.receivables + a.cash)
        e.total_equity_and_liabilities = _r(
            e.equity + e.loans + e.payables + e.other_current_liabilities
        )
        if abs(a.total_assets - e.total_equity_and_liabilities) > 0.5:
            e.other_current_liabilities = _r(
                a.total_assets - e.equity - e.loans - e.payables
            )
            e.total_equity_and_liabilities = _r(
                e.equity + e.loans + e.payables + e.other_current_liabilities
            )
        gen_meta.setdefault("cash_critical_payable_bump_eur", bump)

    # Typical weekly cash settlement — keep history wave scale near open-invoice weeks.
    last_rev = abs(months[-1].income_statement.revenue)
    dso_weeks = max(1.0, float(params.days_sales_outstanding) / 7.0)
    wc_weekly = (abs(receivables) + abs(payables)) / max(dso_weeks, 4.0)
    weekly_flow = max(10_000.0, last_rev / 3.2, wc_weekly * 0.55)

    history = _generate_balance_history(
        as_of=as_of,
        end_cash=last_cash,
        start_cash=months[0].balance_sheet.assets.cash,
        profile=profile,
        weeks=26,
        seed=seed,
        first_month=first_month,
        one_off_events=one_offs,
        weekly_flow_eur=weekly_flow,
    )
    # Enforce exact link to last month cash (VR-07)
    history[-1] = BalanceHistoryPoint(
        week=len(history),
        date=as_of.isoformat(),
        balance=last_cash,
    )

    invoice_texts = inp.invoice_texts
    if invoice_texts is None:
        # Built-in FI stubs when no LLM / --from-text path supplied texts.
        invoice_texts = InvoiceDescriptiveTexts(
            sales_counterparties=list(SALES_COUNTERPARTIES_FI),
            purchase_counterparties=list(PURCHASE_COUNTERPARTIES_FI),
            sales_descriptions=list(SALES_DESCRIPTIONS_FI),
            purchase_descriptions=list(PURCHASE_DESCRIPTIONS_FI),
            language=inp.options.language,
            notes="built-in stub texts",
        )
    # VR-13 / FR-A-32: never emit digits in free-text invoice fields (ids stay numeric).
    invoice_texts = sanitize_invoice_texts_for_pack(invoice_texts)

    invoices = _generate_invoices(
        as_of=as_of,
        receivables=receivables,
        payables=payables,
        dso=params.days_sales_outstanding,
        dpo=params.days_payables_outstanding,
        profile=profile,
        language=inp.options.language,
        seed=seed,
        texts=invoice_texts,
    )

    projection = _project_from_invoices(
        as_of=as_of,
        opening_cash=last_cash,
        invoices=invoices,
        weeks=8,
    )

    currency = inp.options.currency
    monthly = MonthlyReports(
        meta=ScenarioMeta(
            fictional=True,
            dataset="monthly_reports",
            currency=currency,
            scenario=scenario_id,
            note=(
                "Income statement items are VAT 0 %. "
                f"Receivables and payables include VAT ({VAT_RATE_FI * 100:.1f} %)."
            ),
        ),
        months=months,
    )
    cash = CashAndInvoices(
        meta=ScenarioMeta(
            fictional=True,
            dataset="cash_and_invoices",
            currency=currency,
            scenario=scenario_id,
            as_of=as_of.isoformat(),
            note=(
                "Balance history is weekly for the past 26 weeks. "
                "The projection takes into account only the open invoices below "
                "(payroll, tax and other recurring payments are not included)."
            ),
        ),
        balance_history=history,
        open_invoices=invoices,
        projection_from_open_invoices=projection,
    )

    # Stamp pack label on input meta for round-trips (behaviour profile kept in note).
    stamped = inp.model_copy(deep=True)
    stamped.meta.scenario = scenario_id
    stamped.meta.fictional = True
    note_bits = [stamped.meta.note or "", f"behavior_profile={profile}"]
    if gen_meta.get("ending_cash_note"):
        note_bits.append(str(gen_meta["ending_cash_note"]))
    stamped.meta.note = " | ".join(b for b in note_bits if b).strip(" |")
    if stamped.options.scenario_id is None:
        stamped.options.scenario_id = scenario_id
    stamped.invoice_texts = invoice_texts
    # Carry generator meta on a transient attribute for run_log enrichment
    pack = ScenarioPack(input=stamped, monthly_reports=monthly, cash_and_invoices=cash)
    setattr(pack, "_generator_meta", gen_meta)
    return pack


def _balance_sheet_plug(
    *,
    fa: float,
    inventory: float,
    receivables: float,
    cash: float,
    equity: float,
    loans: float,
    payables: float,
    loan_floor: float = 100_000.0,
) -> tuple[float, float, float]:
    """Balance the BS while holding equity and cash fixed.

    Returns ``(fixed_assets, loans, other_current_liabilities)``.
    Negative plug → reduce loans toward ``loan_floor``, then raise FA.
    """
    total_assets = _r(fa + inventory + receivables + cash)
    other_cl = _r(total_assets - equity - loans - payables)
    if other_cl >= -0.5:
        return _r(fa), _r(loans), max(0.0, other_cl) if other_cl < 0 else other_cl

    deficit = _r(-other_cl)
    reducible = max(0.0, loans - loan_floor)
    take = min(deficit, reducible)
    loans = _r(loans - take)
    deficit = _r(deficit - take)
    if deficit > 0.5:
        fa = _r(fa + deficit)
        deficit = 0.0
    total_assets = _r(fa + inventory + receivables + cash)
    other_cl = _r(total_assets - equity - loans - payables)
    if other_cl < -0.5:
        # Cent-level leftover after loan floor: raise FA so the identity holds.
        fa = _r(fa - other_cl)
        total_assets = _r(fa + inventory + receivables + cash)
        other_cl = _r(total_assets - equity - loans - payables)
    if other_cl < 0:
        other_cl = 0.0
    return _r(fa), _r(loans), _r(other_cl)


def _generate_months(
    *,
    first_month: date,
    n: int,
    params,
    profile: str,
    partly_fixed: bool,
    seed: int,
    one_off_events: list[OneOffCashEvent] | None = None,
) -> tuple[list[MonthlyReport], dict[str, Any]]:
    shares = params.cost_shares_of_revenue
    start_rev = params.monthly_revenue_start_eur
    growth = params.monthly_revenue_growth
    vat = 1.0 + VAT_RATE_FI
    factors = list(params.monthly_revenue_factors) if params.monthly_revenue_factors else None
    events = list(one_off_events or [])

    # Opening BS anchors (deterministic, CPU-friendly)
    fixed_assets = 300_000.0
    equity0 = 245_000.0 if profile == "good" else 210_000.0
    loans = 480_000.0
    cash0 = {
        "good": 270_000.0,
        "weak": 265_000.0,
        "cash_critical": 110_000.0,
        "cash_turning_critical_later": 180_000.0,
        "invoices_out_of_balance": 200_000.0,
    }.get(profile, 200_000.0)
    # Thin winter / covenant stories: keep opening cash on the same scale as target
    # so history/projection do not look like a healthy 300k+ pack.
    if profile == "cash_critical" and params.target_cash_at_end_eur <= 60_000:
        cash0 = min(cash0, max(35_000.0, float(params.target_cash_at_end_eur) * 2.2))

    # Fixed cost bases from start revenue
    base_personnel = start_rev * shares.personnel
    base_other = start_rev * shares.other

    dep_monthly = 6_000.0
    interest_annual_rate = 0.045

    months: list[MonthlyReport] = []
    equity = equity0
    cash = cash0
    target_end = params.target_cash_at_end_eur
    # Past one-off events as (month_index_0based, signed_cash_delta)
    past_event_scars: list[tuple[int, float]] = []
    fa_boost = 0.0
    gen_meta: dict[str, Any] = {
        "one_off_events_applied": [],
        "ending_cash_note": None,
        "target_cash_at_end_eur": target_end,
    }

    for i in range(n):
        month_date = _add_months(first_month, i)
        month_index_1based = i + 1
        # Calendar-month seasonality (Jan=0 … Dec=11) when factors provided;
        # otherwise mild sine wiggle for VR-21.
        if factors is not None:
            cal_factor = float(factors[month_date.month - 1])
            seasonal = cal_factor
            # Ensure ≥5% MoM somewhere when factors are nearly flat
            if i == max(2, n // 3) and abs(cal_factor - 1.0) < 0.02:
                seasonal *= 0.92
        else:
            seasonal = 1.0 + 0.045 * math.sin((i + seed % 7) * 0.9)
            if i == max(2, n // 3):
                seasonal *= 0.92  # deliberate ≥5% move vs neighbours
        revenue = _r(start_rev * ((1.0 + growth) ** i) * seasonal)

        materials = _r(revenue * shares.materials)
        services = _r(revenue * shares.services)
        if partly_fixed:
            # Mix variable with start-level fixed costs → losses when revenue falls
            personnel = _r(0.35 * revenue * shares.personnel + 0.65 * base_personnel)
            other = _r(0.35 * revenue * shares.other + 0.65 * base_other)
        else:
            personnel = _r(revenue * shares.personnel)
            other = _r(revenue * shares.other)

        materials_and_services = materials + services
        depreciation = _r(dep_monthly * (0.99**i))
        operating_profit = _r(
            revenue - materials_and_services - personnel - other - depreciation
        )
        interest_expense = _r(loans * interest_annual_rate / 12.0)
        profit_before_tax = _r(operating_profit - interest_expense)
        income_tax = _r(max(0.0, profit_before_tax) * CORPORATE_TAX_RATE)
        net_result = _r(profit_before_tax - income_tax)

        # Working capital from DSO/DPO
        receivables = _r(revenue * (params.days_sales_outstanding / 30.0) * vat)
        payables = _r(materials_and_services * (params.days_payables_outstanding / 30.0) * vat)
        inventory = _r(materials * 0.40)

        # Fixed assets path + one-off capex (out events increase FA)
        month_events = _events_for_month(events, month_index_1based)
        for ev in month_events:
            signed = ev.amount_eur if ev.direction == "in" else -ev.amount_eur
            past_event_scars.append((i, signed))
            if ev.direction == "out":
                fa_boost += ev.amount_eur
            gen_meta["one_off_events_applied"].append(
                {
                    "month_index": month_index_1based,
                    "month": _fmt_month(month_date),
                    "amount_eur": ev.amount_eur,
                    "direction": ev.direction,
                    "label": ev.label,
                }
            )

        fa = fixed_assets + fa_boost - sum(
            _r(dep_monthly * (0.99**j)) for j in range(i + 1)
        )
        fa = max(50_000.0, _r(fa))

        # Cash path toward target via dynamics (not a hard last_cash == target snap).
        # One-off events create a full scar at their month that linearly fades to 0
        # by the final month so parameters still drive ending cash near target.
        t = i / max(1, n - 1)
        if profile == "cash_critical":
            path_shape = t**0.85
        else:
            path_shape = t
        base_path = cash0 + (target_end - cash0) * path_shape
        scar = 0.0
        for event_i, signed in past_event_scars:
            span = max(1, (n - 1) - event_i)
            # At event month: factor 1.0; at final month: factor 0.0
            factor = max(0.0, 1.0 - (i - event_i) / span)
            scar += signed * factor
        cash_path = base_path + scar
        cash = _r(cash_path)

        loan_floor = 100_000.0
        loans = _r(max(loan_floor, 480_000.0 - 5_000.0 * (i + 1)))
        # Equity roll-forward (VR-04 continuity): equity_t = equity_{t-1} + net_result_t.
        # Never absorb a negative BS plug into equity (that broke cash_critical packs).
        equity = _r(
            (equity0 if i == 0 else months[i - 1].balance_sheet.equity_and_liabilities.equity)
            + net_result
        )

        # Plug other current liabilities so BS balances — do NOT drain cash (target
        # path) and do NOT rewrite equity (continuity). Prefer loan reduction, then
        # raise fixed assets as a last resort.
        fa, loans, other_cl = _balance_sheet_plug(
            fa=fa,
            inventory=inventory,
            receivables=receivables,
            cash=cash,
            equity=equity,
            loans=loans,
            payables=payables,
            loan_floor=loan_floor,
        )

        months.append(
            MonthlyReport(
                month=_fmt_month(month_date),
                income_statement=IncomeStatement(
                    revenue=revenue,
                    materials_and_services=materials_and_services,
                    personnel_costs=personnel,
                    other_operating_costs=other,
                    depreciation=depreciation,
                    operating_profit=operating_profit,
                    interest_expense=interest_expense,
                    profit_before_tax=profit_before_tax,
                    income_tax=income_tax,
                    net_result=net_result,
                ),
                balance_sheet=BalanceSheet(
                    assets=Assets(
                        fixed_assets=_r(fa),
                        inventory=inventory,
                        receivables=receivables,
                        cash=cash,
                        total_assets=_r(fa + inventory + receivables + cash),
                    ),
                    equity_and_liabilities=EquityAndLiabilities(
                        equity=equity,
                        loans=loans,
                        payables=payables,
                        other_current_liabilities=other_cl,
                        total_equity_and_liabilities=_r(
                            equity + loans + payables + other_cl
                        ),
                    ),
                ),
            )
        )

        # Ensure totals match after construction without touching equity.
        a = months[-1].balance_sheet.assets
        e = months[-1].balance_sheet.equity_and_liabilities
        if abs(a.total_assets - e.total_equity_and_liabilities) > 0.5:
            fa2, loans2, ocl2 = _balance_sheet_plug(
                fa=a.fixed_assets,
                inventory=a.inventory,
                receivables=a.receivables,
                cash=a.cash,
                equity=e.equity,
                loans=e.loans,
                payables=e.payables,
                loan_floor=loan_floor,
            )
            a.fixed_assets = fa2
            a.total_assets = _r(fa2 + a.inventory + a.receivables + a.cash)
            e.loans = loans2
            e.other_current_liabilities = ocl2
            e.total_equity_and_liabilities = _r(
                e.equity + e.loans + e.payables + e.other_current_liabilities
            )

    final_cash = months[-1].balance_sheet.assets.cash if months else None
    if final_cash is not None:
        gap = _r(final_cash - target_end)
        gen_meta["ending_cash_eur"] = final_cash
        gen_meta["ending_cash_vs_target_eur"] = gap
        gen_meta["ending_cash_note"] = (
            f"ending_cash_via_dynamics={final_cash} "
            f"(target={target_end}, delta={gap}); "
            "parameters drive ending cash — not forced exact equality"
        )

    return months, gen_meta


def _generate_balance_history(
    *,
    as_of: date,
    end_cash: float,
    start_cash: float,
    profile: str,
    weeks: int,
    seed: int,
    first_month: date | None = None,
    one_off_events: list[OneOffCashEvent] | None = None,
    weekly_flow_eur: float = 8_000.0,
) -> list[BalanceHistoryPoint]:
    """
    Build 26-week balance history.

    One-off events (e.g. €95k roof repair) punch a discrete step into the week
    nearest the event month-end so the outflow is visible in weekly history even
    when the calendar month falls near/before the history window.

    ``weekly_flow_eur`` sizes the settlement wave so history week moves stay in the
    same order of magnitude as open-invoice projection weeks (VR-08 scale).
    """
    # Map one-off events → week index (1..weeks)
    event_by_week: dict[int, float] = {}
    if one_off_events and first_month is not None:
        hist_start = as_of - timedelta(days=7 * (weeks - 1))
        for ev in one_off_events:
            event_month = _add_months(first_month, ev.month_index - 1)
            event_day = _month_end(event_month)
            signed = ev.amount_eur if ev.direction == "in" else -ev.amount_eur
            if event_day < hist_start:
                # Still show the outflow: place near the start of the history window
                w = 2
            elif event_day >= as_of:
                w = max(2, weeks - 1)
            else:
                delta_days = (event_day - hist_start).days
                w = int(round(delta_days / 7.0)) + 1
                w = min(weeks - 1, max(2, w))
            event_by_week[w] = event_by_week.get(w, 0.0) + signed

    flow = max(5_000.0, float(weekly_flow_eur))
    points: list[BalanceHistoryPoint] = []
    for week_idx in range(1, weeks + 1):
        w_from_end = weeks - week_idx  # 25..0
        d = as_of - timedelta(days=7 * w_from_end)
        t = (week_idx - 1) / max(1, weeks - 1)
        base = start_cash + (end_cash - start_cash) * t
        # Settlement-scale wave + occasional pulse (not a flat ±4k sine).
        wave = flow * 0.7 * math.sin((week_idx + seed) * 0.55)
        pulse = 0.0
        if week_idx % 3 == (seed % 3) and week_idx not in (1, weeks):
            pulse = flow * (0.45 if (week_idx // 3) % 2 == 0 else -0.3)
        if profile == "good":
            bal = base + abs(wave) * 0.55 + pulse * 0.65
        elif profile == "weak":
            bal = base - abs(wave) * 0.4 + pulse * 0.45
        elif profile == "cash_turning_critical_later":
            if week_idx < 18:
                bal = start_cash - (start_cash - 40_000.0) * (week_idx / 18.0) * 0.35
                bal = bal + wave * 0.2 + pulse * 0.35
            elif week_idx <= 22:
                bal = 15_000.0 - 8_000.0 * (week_idx - 18)
            else:
                bal = base + wave * 0.15
        else:
            bal = base + wave * 0.3 + pulse * 0.4
        # One-off events: single-week step (visible outflow/inflow), not a lasting drag.
        # Week-to-week delta ≈ event amount; following weeks resume the base path.
        if week_idx in event_by_week and week_idx < weeks:
            bal = bal + event_by_week[week_idx]
        if week_idx == weeks:
            bal = end_cash
        points.append(
            BalanceHistoryPoint(week=week_idx, date=d.isoformat(), balance=_r(bal))
        )
    return points


def _split_amounts(total: float, n: int, seed: int) -> list[float]:
    """Split total into n positive parts that sum exactly to total."""
    weights = [0.7 + ((seed * (i + 3) * 17) % 100) / 100.0 for i in range(n)]
    s = sum(weights)
    raw = [total * w / s for w in weights]
    rounded = [_r(x) for x in raw]
    drift = _r(total - sum(rounded))
    rounded[-1] = _r(rounded[-1] + drift)
    # Fix non-positive last slice
    if rounded[-1] <= 0:
        for i in range(n - 1):
            if rounded[i] > 2 + abs(rounded[-1]):
                rounded[i] = _r(rounded[i] + rounded[-1] - 1)
                rounded[-1] = 1.0
                break
    return rounded


def _due_in_projection_week(as_of: date, week: int, *, day_in_week: int = 3) -> date:
    """Return a calendar due date that maps to projection week ``week`` (1-based)."""
    week = max(1, int(week))
    day = min(6, max(1, int(day_in_week)))
    return as_of + timedelta(days=7 * (week - 1) + day)


def _spread_weeks(n: int, first: int, last: int) -> list[int]:
    """Evenly spread ``n`` items across inclusive week indices first..last."""
    first = max(1, int(first))
    last = max(first, int(last))
    span = last - first + 1
    if n <= 0:
        return []
    if n == 1:
        return [first]
    return [first + (i * (span - 1)) // (n - 1) for i in range(n)]


def _generate_invoices(
    *,
    as_of: date,
    receivables: float,
    payables: float,
    dso: float,
    dpo: float,
    profile: str,
    language: str,
    seed: int,
    texts: InvoiceDescriptiveTexts,
) -> list[OpenInvoice]:
    # FR-A-23: 15–25 invoices total, split sales/purchases
    total_n = 15 + (seed % 11)  # 15..25
    n_sales = max(7, total_n // 2)
    n_purch = total_n - n_sales
    sales_amts = _split_amounts(receivables, n_sales, seed)
    purch_amts = _split_amounts(payables, n_purch, seed + 9)

    sales_cp = texts.sales_counterparties or SALES_COUNTERPARTIES_FI
    purch_cp = texts.purchase_counterparties or PURCHASE_COUNTERPARTIES_FI
    sales_desc = texts.sales_descriptions or SALES_DESCRIPTIONS_FI
    purch_desc = texts.purchase_descriptions or PURCHASE_DESCRIPTIONS_FI

    # Projection horizon for due staggering (keep weekly moves near history scale).
    # Start open (non-overdue) dues at week 2 so week-1 is not overdue+open piled up.
    sales_last_w = min(8, max(4, int(math.ceil(float(dso) / 7.0))))
    purch_last_w = min(8, max(4, int(math.ceil(float(dpo) / 7.0))))
    sales_weeks = _spread_weeks(max(0, n_sales - 1), 2, sales_last_w)
    purch_weeks = _spread_weeks(n_purch, 2, purch_last_w)

    invoices: list[OpenInvoice] = []

    # Sales: mix of overdue + future dues
    for i, amt in enumerate(sales_amts):
        if profile == "cash_critical":
            if i == 0:
                # One overdue → week-1 inflow
                issue = as_of - timedelta(days=int(dso) + 10)
                due = as_of - timedelta(days=17)
                status = "overdue"
            elif i <= 2:
                # Due in week 4 (after the purchase cliff)
                issue = as_of - timedelta(days=5)
                due = as_of + timedelta(days=21 + i * 3)
                status = "open"
            else:
                # Remaining collections after the cliff, still inside 8 weeks
                w = 5 + ((i - 3) % 4)  # weeks 5–8
                due = _due_in_projection_week(as_of, w, day_in_week=2 + (i % 4))
                issue = due - timedelta(days=int(dso))
                status = "open"
        elif profile == "cash_turning_critical_later":
            # Near-term projection must stay solvent (crisis lives in history ~week 20).
            # Stagger collections across weeks 1–8 so purchases never cliff first.
            if i == 0:
                issue = as_of - timedelta(days=int(dso) + 3)
                due = as_of - timedelta(days=2)
                status = "overdue"
            else:
                w = sales_weeks[i - 1] if i - 1 < len(sales_weeks) else sales_last_w
                due = _due_in_projection_week(as_of, w, day_in_week=2 + (i % 4))
                issue = due - timedelta(days=max(14, int(dso) // 2))
                status = "open"
        elif profile == "weak":
            if i == 0:
                issue = as_of - timedelta(days=int(dso) + 5)
                due = as_of - timedelta(days=5)
                status = "overdue"
            else:
                w = sales_weeks[i - 1] if i - 1 < len(sales_weeks) else sales_last_w
                due = _due_in_projection_week(as_of, w, day_in_week=1 + (i % 5))
                issue = due - timedelta(days=int(dso))
                status = "open" if due >= as_of else "overdue"
        else:  # good / default — spread dues to avoid one 180k+ week
            if i == 0:
                issue = as_of - timedelta(days=int(dso) + 3)
                due = as_of - timedelta(days=2)
                status = "overdue"
            else:
                w = sales_weeks[i - 1] if i - 1 < len(sales_weeks) else sales_last_w
                due = _due_in_projection_week(as_of, w, day_in_week=2 + (i % 4))
                issue = due - timedelta(days=int(dso))
                if issue > as_of:
                    issue = as_of - timedelta(days=1 + (i % 5))
                status = "open" if due >= as_of else "overdue"

        net, vat, gross = _vat_split(amt)
        invoices.append(
            OpenInvoice(
                id=f"S-{2600 + i}",
                type="sales",
                counterparty=pick(list(sales_cp), i),
                description=pick(list(sales_desc), i),
                issue_date=issue.isoformat(),
                due_date=due.isoformat(),
                amount_incl_vat=gross,
                amount_net_eur=net,
                vat_eur=vat,
                status=status,  # type: ignore[arg-type]
            )
        )

    # Purchases
    for i, amt in enumerate(purch_amts):
        if profile == "cash_critical":
            # Cluster large outflows in week 3 (days 15–21 after as_of)
            issue = as_of - timedelta(days=10 + (i % 5))
            due = as_of + timedelta(days=15 + (i % 6))  # ~Nov 15–21 if as_of Oct 31
            status = "open"
        elif profile == "cash_turning_critical_later":
            # Spread supplier dues across weeks 2–7 (no early cliff before sales).
            w = purch_weeks[i] if i < len(purch_weeks) else purch_last_w
            w = min(7, max(2, w))
            due = _due_in_projection_week(as_of, w, day_in_week=1 + (i % 5))
            issue = due - timedelta(days=int(dpo))
            status = "open" if due >= as_of else "overdue"
        elif profile == "weak":
            w = purch_weeks[i] if i < len(purch_weeks) else purch_last_w
            due = _due_in_projection_week(as_of, w, day_in_week=2 + (i % 4))
            issue = as_of - timedelta(days=5 + (i % 6))
            status = "open" if due >= as_of else "overdue"
        else:
            # good / default — spread across DPO window
            w = purch_weeks[i] if i < len(purch_weeks) else purch_last_w
            due = _due_in_projection_week(as_of, w, day_in_week=1 + (i % 5))
            issue = due - timedelta(days=int(dpo))
            if issue > as_of:
                issue = as_of - timedelta(days=2 + (i % 4))
            status = "open" if due >= as_of else "overdue"

        net, vat, gross = _vat_split(amt)
        invoices.append(
            OpenInvoice(
                id=f"P-{2650 + i}",
                type="purchase",
                counterparty=pick(list(purch_cp), i),
                description=pick(list(purch_desc), i),
                issue_date=issue.isoformat(),
                due_date=due.isoformat(),
                amount_incl_vat=gross,
                amount_net_eur=net,
                vat_eur=vat,
                status=status,  # type: ignore[arg-type]
            )
        )

    # Re-balance exact AR/AP sums after status logic (amounts already split)
    sales_sum = sum(x.amount_incl_vat for x in invoices if x.type == "sales")
    purch_sum = sum(x.amount_incl_vat for x in invoices if x.type == "purchase")
    if abs(sales_sum - receivables) > 0.02:
        for inv in reversed(invoices):
            if inv.type == "sales":
                new_gross = _r(inv.amount_incl_vat + (receivables - sales_sum))
                net, vat, gross = _vat_split(new_gross)
                inv.amount_incl_vat = gross
                inv.amount_net_eur = net
                inv.vat_eur = vat
                break
    if abs(purch_sum - payables) > 0.02:
        for inv in reversed(invoices):
            if inv.type == "purchase":
                new_gross = _r(inv.amount_incl_vat + (payables - purch_sum))
                net, vat, gross = _vat_split(new_gross)
                inv.amount_incl_vat = gross
                inv.amount_net_eur = net
                inv.vat_eur = vat
                break

    _ = language  # texts.language already selected by caller / LLM
    return invoices


def _week_index(as_of: date, due: date, weeks: int) -> int | None:
    """Map a due date to projection week 1..weeks. Overdue sales handled separately."""
    # Week 1 ends as_of + 7, week 2 ends as_of + 14, ...
    if due <= as_of:
        return None  # overdue — caller decides
    delta = (due - as_of).days
    w = math.ceil(delta / 7.0)
    if w < 1:
        w = 1
    if w > weeks:
        return None
    return w


def _project_from_invoices(
    *,
    as_of: date,
    opening_cash: float,
    invoices: list[OpenInvoice],
    weeks: int,
) -> list[ProjectionWeek]:
    sales = [0.0] * weeks
    purch = [0.0] * weeks

    for inv in invoices:
        due = date.fromisoformat(inv.due_date)
        if inv.type == "sales":
            if inv.status == "overdue" or due <= as_of:
                sales[0] += inv.amount_incl_vat
            else:
                w = _week_index(as_of, due, weeks)
                if w is not None:
                    sales[w - 1] += inv.amount_incl_vat
        else:
            if due <= as_of:
                purch[0] += inv.amount_incl_vat
            else:
                w = _week_index(as_of, due, weeks)
                if w is not None:
                    purch[w - 1] += inv.amount_incl_vat

    bal = opening_cash
    out: list[ProjectionWeek] = []
    for i in range(weeks):
        week_end = as_of + timedelta(days=7 * (i + 1))
        si = _r(sales[i])
        po = _r(purch[i])
        bal = _r(bal + si - po)
        out.append(
            ProjectionWeek(
                week=i + 1,
                week_end=week_end.isoformat(),
                sales_inflow=si,
                purchase_outflow=po,
                projected_balance=bal,
            )
        )
    return out


def write_pack(
    pack: ScenarioPack,
    out_dir: Path,
    *,
    write_xlsx: bool = True,
    write_journal: bool = True,
    seed: int = 42,
    software_version: str | None = None,
    raw_llm_output: str | None = None,
    llm_name: str | None = None,
    validation: dict | None = None,
    seed_attempts: list | None = None,
    number_of_retries: int = 0,
    param_clips: list | None = None,
    test_only_broken: bool = False,
    write_data_files: bool = True,
) -> Path:
    """Write SRS §6.6 folder (JSON + scenario.xlsx + answer_key + run_log)."""
    import json
    from datetime import datetime, timezone

    from payloq_generator.answer_key import build_answer_key
    from payloq_schemas.constants import SOFTWARE_VERSION

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if write_journal and pack.journal_entries is None and write_data_files:
        from payloq_generator.journal import build_journal_entries

        pack = pack.model_copy(update={"journal_entries": build_journal_entries(pack)})

    answer_key = build_answer_key(pack) if write_data_files else None
    ver = software_version or SOFTWARE_VERSION
    gen_meta = getattr(pack, "_generator_meta", None) or {}
    run_log = {
        "software_version": ver,
        "seed": seed,
        "language_model_name": llm_name,
        "run_time": datetime.now(timezone.utc).isoformat(),
        "validation_result": (validation or {}).get("validation_result", "unknown"),
        "validation": validation,
        "number_of_retries": number_of_retries,
        "seed_attempts": seed_attempts or [{"seed": seed, "ok": (validation or {}).get("ok")}],
        "parameter_clips": param_clips or [],
        "parameters": pack.input.parameters_from_language_model.model_dump(),
        "options": pack.input.options.model_dump(),
        "pack_label": pack.input.options.scenario_id or pack.input.meta.scenario,
        "behavior_profile": (
            (pack.input.meta.note or "").split("behavior_profile=")[-1].split("|")[0].strip()
            if pack.input.meta.note and "behavior_profile=" in (pack.input.meta.note or "")
            else None
        ),
        "ending_cash": gen_meta.get("ending_cash_note")
        or {
            "ending_cash_eur": gen_meta.get("ending_cash_eur"),
            "target_cash_at_end_eur": gen_meta.get("target_cash_at_end_eur"),
            "delta_eur": gen_meta.get("ending_cash_vs_target_eur"),
            "note": "parameters drive ending cash via dynamics; not forced exact equality",
        },
        "one_off_events_applied": gen_meta.get("one_off_events_applied") or [],
        "test_only_broken": test_only_broken or False,
        "python_version": __import__("sys").version.split()[0],
    }

    # Always write run_log (even on validation failure — VR-30 reason trail)
    (out_dir / "run_log.json").write_text(
        json.dumps(run_log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if raw_llm_output is not None:
        (out_dir / "raw_llm_output.txt").write_text(raw_llm_output, encoding="utf-8")

    if not write_data_files:
        return out_dir

    (out_dir / "input.json").write_text(
        pack.input.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "monthly_reports.json").write_text(
        pack.monthly_reports.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "cash_and_invoices.json").write_text(
        pack.cash_and_invoices.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    if answer_key is not None:
        (out_dir / "answer_key.json").write_text(
            json.dumps(answer_key, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    if pack.journal_entries is not None:
        (out_dir / "journal_entries.json").write_text(
            pack.journal_entries.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )

    if write_xlsx:
        from payloq_export_xlsx.writer import write_scenario_xlsx

        scenario = pack.input.options.scenario_id or pack.input.meta.scenario or "scenario"
        # SRS §6.6 canonical name
        write_scenario_xlsx(
            pack,
            out_dir / "scenario.xlsx",
            include_journal=pack.journal_entries is not None,
        )
        # Backward-compatible alias for older app/tests
        write_scenario_xlsx(
            pack,
            out_dir / f"scenario_{scenario}.xlsx",
            include_journal=pack.journal_entries is not None,
        )

    return out_dir


def break_receivables_mismatch(pack: ScenarioPack, *, delta_eur: float = 2_100.0) -> ScenarioPack:
    """Deliberately break VR-05 for TEST_ONLY_BROKEN (scenario 9.5)."""
    pack = pack.model_copy(deep=True)
    sales = [i for i in pack.cash_and_invoices.open_invoices if i.type == "sales"]
    if not sales:
        return pack
    # Shrink open sales totals without changing balance-sheet receivables
    remaining = delta_eur
    for inv in sales:
        if remaining <= 0:
            break
        cut = min(remaining, max(0.0, inv.amount_incl_vat - 1.0))
        new_gross = _r(inv.amount_incl_vat - cut)
        net, vat, gross = _vat_split(new_gross)
        inv.amount_incl_vat = gross
        inv.amount_net_eur = net
        inv.vat_eur = vat
        remaining = _r(remaining - cut)
    # Keep projection consistent with (broken) invoices so only VR-05 fails
    as_of_s = pack.cash_and_invoices.meta.as_of
    if as_of_s:
        from datetime import date as _date

        last_cash = pack.monthly_reports.months[-1].balance_sheet.assets.cash
        pack.cash_and_invoices.projection_from_open_invoices = _project_from_invoices(
            as_of=_date.fromisoformat(as_of_s),
            opening_cash=last_cash,
            invoices=pack.cash_and_invoices.open_invoices,
            weeks=8,
        )
    note = pack.input.meta.note or ""
    pack.input.meta.note = (note + " TEST_ONLY_BROKEN: receivables ≠ Σ sales invoices.").strip()
    pack.input.meta.scenario = "invoices_out_of_balance"
    if pack.input.options.scenario_id:
        pack.input.options.scenario_id = "invoices_out_of_balance"
    return pack


def load_input(path: Path) -> GeneratorInput:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return GeneratorInput.model_validate(data)

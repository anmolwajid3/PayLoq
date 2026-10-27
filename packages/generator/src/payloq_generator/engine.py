"""Params → monthly reports, cash history, open invoices, projection."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

from payloq_schemas.constants import CORPORATE_TAX_RATE, VAT_RATE_FI
from payloq_schemas.models import (
    Assets,
    BalanceHistoryPoint,
    BalanceSheet,
    CashAndInvoices,
    EquityAndLiabilities,
    GeneratorInput,
    IncomeStatement,
    MonthlyReport,
    MonthlyReports,
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


def _r(value: float) -> float:
    """Round money to whole euros (matches example style)."""
    return float(round(value))


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


def _infer_profile(inp: GeneratorInput) -> str:
    sid = (inp.options.scenario_id or inp.meta.scenario or "").strip().lower()
    if sid in {"good", "weak", "cash_critical"}:
        return sid
    g = inp.parameters_from_language_model.monthly_revenue_growth
    cash = inp.parameters_from_language_model.target_cash_at_end_eur
    if g < -0.005:
        return "weak"
    if cash <= 60_000:
        return "cash_critical"
    return "good"


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
    scenario_id = inp.options.scenario_id or inp.meta.scenario or profile

    partly_fixed = params.partly_fixed_costs or profile in {"weak", "cash_critical"}

    months = _generate_months(
        first_month=first_month,
        n=n,
        params=params,
        profile=profile,
        partly_fixed=partly_fixed,
        seed=seed,
    )

    last_bs = months[-1].balance_sheet
    last_cash = last_bs.assets.cash
    receivables = last_bs.assets.receivables
    payables = last_bs.equity_and_liabilities.payables

    history = _generate_balance_history(
        as_of=as_of,
        end_cash=last_cash,
        start_cash=months[0].balance_sheet.assets.cash,
        profile=profile,
        weeks=26,
        seed=seed,
    )
    # Enforce exact link to last month cash
    history[-1] = BalanceHistoryPoint(date=as_of.isoformat(), balance=last_cash)

    invoices = _generate_invoices(
        as_of=as_of,
        receivables=receivables,
        payables=payables,
        dso=params.days_sales_outstanding,
        dpo=params.days_payables_outstanding,
        profile=profile,
        language=inp.options.language,
        seed=seed,
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

    # Stamp scenario id on input meta for round-trips
    stamped = inp.model_copy(deep=True)
    stamped.meta.scenario = scenario_id
    stamped.meta.fictional = True
    if stamped.options.scenario_id is None:
        stamped.options.scenario_id = scenario_id

    return ScenarioPack(input=stamped, monthly_reports=monthly, cash_and_invoices=cash)


def _generate_months(
    *,
    first_month: date,
    n: int,
    params,
    profile: str,
    partly_fixed: bool,
    seed: int,
) -> list[MonthlyReport]:
    shares = params.cost_shares_of_revenue
    start_rev = params.monthly_revenue_start_eur
    growth = params.monthly_revenue_growth
    vat = 1.0 + VAT_RATE_FI

    # Opening BS anchors (deterministic, CPU-friendly)
    fixed_assets = 300_000.0
    if params.special_investment_eur:
        # Investment lands mid-horizon (month index ~3)
        pass
    equity0 = 245_000.0 if profile == "good" else 210_000.0
    loans = 480_000.0
    cash0 = {
        "good": 270_000.0,
        "weak": 265_000.0,
        "cash_critical": 110_000.0,
    }.get(profile, 200_000.0)

    # Fixed cost bases from start revenue
    base_personnel = start_rev * shares.personnel
    base_other = start_rev * shares.other

    dep_monthly = 6_000.0
    interest_annual_rate = 0.045

    months: list[MonthlyReport] = []
    equity = equity0
    cash = cash0
    target_end = params.target_cash_at_end_eur

    for i in range(n):
        month_date = _add_months(first_month, i)
        # Mild seasonal wiggle (deterministic sine) — behavioural, not golden match
        seasonal = 1.0 + 0.02 * math.sin((i + seed % 7) * 0.9)
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

        # Fixed assets path + one-off investment
        fa = fixed_assets - sum(
            _r(dep_monthly * (0.99**j)) for j in range(i + 1)
        )
        if params.special_investment_eur and i == max(2, n // 4):
            fa += params.special_investment_eur
            cash -= params.special_investment_eur
        fa = max(50_000.0, _r(fa))

        # Cash path toward target (linear-ish with profile stress)
        t = i / max(1, n - 1)
        if profile == "cash_critical":
            # Drift down early, settle near target
            cash_path = cash0 + (target_end - cash0) * (t**0.85)
        elif profile == "weak":
            cash_path = cash0 + (target_end - cash0) * t
        else:
            cash_path = cash0 + (target_end - cash0) * t
        cash = _r(cash_path)
        if i == n - 1:
            cash = _r(target_end)

        loans = _r(max(100_000.0, 480_000.0 - 5_000.0 * (i + 1)))
        equity = _r((equity0 if i == 0 else months[i - 1].balance_sheet.equity_and_liabilities.equity) + net_result)

        assets_sum_wo_plug = fa + inventory + receivables + cash
        # Plug other current liabilities so BS balances
        other_cl = _r(assets_sum_wo_plug - equity - loans - payables)
        if other_cl < 5_000:
            # Shift residual into cash so liabilities stay non-negative
            deficit = 5_000 - other_cl
            cash = _r(cash - deficit)
            if i == n - 1:
                # Prefer exact target cash on final month: reduce equity plug via other_cl
                cash = _r(target_end)
                assets_sum_wo_plug = fa + inventory + receivables + cash
                other_cl = _r(assets_sum_wo_plug - equity - loans - payables)
            else:
                assets_sum_wo_plug = fa + inventory + receivables + cash
                other_cl = _r(assets_sum_wo_plug - equity - loans - payables)

        total_assets = _r(fa + inventory + receivables + cash)
        total_el = _r(equity + loans + payables + other_cl)
        # Final cent-level reconcile on cash if needed
        if abs(total_assets - total_el) > 0.5:
            cash = _r(cash + (total_el - total_assets))
            if i == n - 1:
                # Keep target cash; adjust other_cl instead
                cash = _r(target_end)
                total_assets = _r(fa + inventory + receivables + cash)
                other_cl = _r(total_assets - equity - loans - payables)
                total_el = _r(equity + loans + payables + other_cl)
            else:
                total_assets = _r(fa + inventory + receivables + cash)

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

        # Ensure totals match after construction
        a = months[-1].balance_sheet.assets
        e = months[-1].balance_sheet.equity_and_liabilities
        if abs(a.total_assets - e.total_equity_and_liabilities) > 0.5:
            e.other_current_liabilities = _r(
                a.total_assets - e.equity - e.loans - e.payables
            )
            e.total_equity_and_liabilities = _r(
                e.equity + e.loans + e.payables + e.other_current_liabilities
            )

    return months


def _generate_balance_history(
    *,
    as_of: date,
    end_cash: float,
    start_cash: float,
    profile: str,
    weeks: int,
    seed: int,
) -> list[BalanceHistoryPoint]:
    points: list[BalanceHistoryPoint] = []
    # Align week ends to Saturdays like examples (2026-10-31 is Saturday)
    # Walk back weekly from as_of
    for w in range(weeks - 1, -1, -1):
        d = as_of - timedelta(days=7 * w)
        t = (weeks - 1 - w) / max(1, weeks - 1)
        # Interpolate with small wave
        base = start_cash + (end_cash - start_cash) * t
        wave = 4_000.0 * math.sin((w + seed) * 0.55)
        if profile == "good":
            bal = base + abs(wave) * 0.3
        elif profile == "weak":
            bal = base - abs(wave) * 0.2
        else:
            bal = base + wave * 0.15
        if w == 0:
            bal = end_cash
        points.append(BalanceHistoryPoint(date=d.isoformat(), balance=_r(bal)))
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
) -> list[OpenInvoice]:
    n_sales, n_purch = 10, 10
    sales_amts = _split_amounts(receivables, n_sales, seed)
    purch_amts = _split_amounts(payables, n_purch, seed + 9)

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
                issue = as_of + timedelta(days=i)
                due = issue + timedelta(days=int(dso))
                status = "open"
        elif profile == "weak":
            if i == 0:
                issue = as_of - timedelta(days=int(dso) + 5)
                due = as_of - timedelta(days=5)
                status = "overdue"
            else:
                issue = as_of - timedelta(days=max(0, int(dso) - i * 3))
                due = issue + timedelta(days=int(dso))
                status = "open" if due >= as_of else "overdue"
        else:  # good
            if i == 0:
                issue = as_of - timedelta(days=int(dso) + 3)
                due = as_of - timedelta(days=2)
                status = "overdue"
            else:
                issue = as_of - timedelta(days=max(0, 20 - i * 2))
                due = issue + timedelta(days=int(dso))
                status = "open" if due >= as_of else "overdue"

        invoices.append(
            OpenInvoice(
                id=f"S-{2600 + i}",
                type="sales",
                counterparty=pick(SALES_COUNTERPARTIES_FI, i),
                description=pick(SALES_DESCRIPTIONS_FI, i),
                issue_date=issue.isoformat(),
                due_date=due.isoformat(),
                amount_incl_vat=amt,
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
        elif profile == "weak":
            issue = as_of - timedelta(days=5 + i)
            due = as_of + timedelta(days=3 + i * 4)
            status = "open" if due >= as_of else "overdue"
        else:
            issue = as_of - timedelta(days=8 + (i % 4))
            due = issue + timedelta(days=int(dpo))
            status = "open" if due >= as_of else "overdue"

        invoices.append(
            OpenInvoice(
                id=f"P-{2650 + i}",
                type="purchase",
                counterparty=pick(PURCHASE_COUNTERPARTIES_FI, i),
                description=pick(PURCHASE_DESCRIPTIONS_FI, i),
                issue_date=issue.isoformat(),
                due_date=due.isoformat(),
                amount_incl_vat=amt,
                status=status,  # type: ignore[arg-type]
            )
        )

    # Re-balance exact AR/AP sums after status logic (amounts already split)
    sales_sum = sum(x.amount_incl_vat for x in invoices if x.type == "sales")
    purch_sum = sum(x.amount_incl_vat for x in invoices if x.type == "purchase")
    if abs(sales_sum - receivables) > 0.5:
        for inv in reversed(invoices):
            if inv.type == "sales":
                inv.amount_incl_vat = _r(inv.amount_incl_vat + (receivables - sales_sum))
                break
    if abs(purch_sum - payables) > 0.5:
        for inv in reversed(invoices):
            if inv.type == "purchase":
                inv.amount_incl_vat = _r(inv.amount_incl_vat + (payables - purch_sum))
                break

    _ = language  # FI texts used for both; EN labels live in Excel export
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


def write_pack(pack: ScenarioPack, out_dir: Path, *, write_xlsx: bool = True) -> Path:
    """Write JSON (+ optional XLSX) into out_dir. Returns out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "input.json").write_text(
        pack.input.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "monthly_reports.json").write_text(
        pack.monthly_reports.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "cash_and_invoices.json").write_text(
        pack.cash_and_invoices.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )

    if write_xlsx:
        from payloq_export_xlsx.writer import write_scenario_xlsx

        scenario = pack.input.options.scenario_id or pack.input.meta.scenario or "scenario"
        write_scenario_xlsx(pack, out_dir / f"scenario_{scenario}.xlsx")

    return out_dir


def load_input(path: Path) -> GeneratorInput:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return GeneratorInput.model_validate(data)

"""Checks A–G. Decisions come from the four output JSON files."""

from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from harness.scenarios import SEEDS, Case, build_case

FILES: tuple[str, ...] = (
    "input.json",
    "monthly_reports.json",
    "cash_and_invoices.json",
    "answer_key.json",
)
MONEY = 0.02
NOISE = 0.021  # work-order revenue noise band is 0.02; allow a cent of rounding


@dataclass
class Failure:
    check: str
    expected: str
    actual: str
    file: str

    def as_dict(self, *, scenario: str, seed: int) -> dict[str, Any]:
        return {
            "scenario": scenario,
            "seed": seed,
            "check": self.check,
            "expected": self.expected,
            "actual": self.actual,
            "file": self.file,
        }


def _sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(out: Path) -> tuple[dict[str, Any] | None, list[str]]:
    missing = [name for name in FILES if not (out / name).is_file()]
    if missing:
        return None, missing
    loaded = {name: json.loads((out / name).read_text(encoding="utf-8")) for name in FILES}
    return loaded, []


def _near(a: float, b: float, tol: float = MONEY) -> bool:
    return abs(float(a) - float(b)) <= tol


def _band(actual: float, expected: float, frac: float = NOISE) -> bool:
    denom = max(abs(expected), 1.0)
    return abs(actual - expected) / denom <= frac


def _params(data: dict[str, Any]) -> dict[str, Any]:
    return dict(data["input.json"]["parameters_from_language_model"])


def _sources(params: dict[str, Any]) -> dict[str, str]:
    raw = params.get("field_sources") or {}
    return {str(k): str(v) for k, v in raw.items()}


def _fail(check: str, expected: str, actual: str, file: str) -> Failure:
    return Failure(check=check, expected=expected, actual=actual, file=file)


def _month_add(yyyy_mm: str) -> str:
    year, month = (int(part) for part in yyyy_mm.split("-"))
    month += 1
    if month > 12:
        year += 1
        month = 1
    return f"{year:04d}-{month:02d}"


def _sum_invoices(cash: dict[str, Any], kind: str) -> float:
    total = 0.0
    for inv in cash.get("open_invoices") or []:
        if inv.get("type") == kind:
            total += float(inv.get("amount_incl_vat") or 0.0)
    return round(total, 2)


def _chain_ok(projection: list[dict[str, Any]], opening: float) -> str | None:
    bal = float(opening)
    for week in projection:
        bal = round(bal + float(week["sales_inflow"]) - float(week["purchase_outflow"]), 2)
        got = round(float(week["projected_balance"]), 2)
        if not _near(got, bal):
            return f"week {week.get('week')}: projected_balance {got} != chained {bal}"
    return None


def _dates_step(dates: list[str], *, file: str) -> str | None:
    parsed = [date.fromisoformat(item) for item in dates]
    for prev, cur in itertools.pairwise(parsed):
        if (cur - prev).days != 7:
            return f"{file}: {prev.isoformat()} then {cur.isoformat()} is not 7 days"
    return None


def check_status(case: Case, out: Path, call_error: str | None) -> list[Failure]:
    data, missing = _load(out)
    if missing:
        detail = "missing " + ", ".join(missing)
        if call_error:
            detail = f"{detail}; call error: {call_error}"
        return [
            _fail(
                "status",
                "four output files written (run status ok)",
                detail,
                missing[0],
            )
        ]
    assert data is not None
    failures: list[Failure] = []
    options = data["input.json"].get("options") or {}
    months = data["monthly_reports.json"].get("months") or []
    if int(options.get("months") or 0) != case.months or len(months) != case.months:
        failures.append(
            _fail(
                "status",
                f"{case.months} months",
                f"options.months={options.get('months')} monthly rows={len(months)}",
                "monthly_reports.json",
            )
        )
    if str(options.get("language") or "") != case.language:
        failures.append(
            _fail(
                "status",
                case.language,
                str(options.get("language")),
                "input.json",
            )
        )
    if case.scenario_id and str(options.get("scenario_id") or "") != case.scenario_id:
        failures.append(
            _fail(
                "status",
                f"scenario_id {case.scenario_id}",
                str(options.get("scenario_id")),
                "input.json",
            )
        )
    desc = (data["input.json"].get("scenario_description") or {}).get(
        "fi" if case.language == "fi" else "en", ""
    )
    if case.text not in str(desc) and str(desc) not in case.text:
        failures.append(
            _fail(
                "status",
                "description stored in the output",
                str(desc)[:180],
                "input.json",
            )
        )
    if case.cash_shape:
        failures.extend(_cash_shape(case, data))
    return failures


def _cash_shape(case: Case, data: dict[str, Any]) -> list[Failure]:
    cash = data["cash_and_invoices.json"]
    history = cash.get("balance_history") or []
    projection = cash.get("projection_from_open_invoices") or []
    if case.cash_shape == "critical_early":
        early_hist = [p for p in history if int(p["week"]) <= 5 and float(p["balance"]) < 0]
        early_proj = [
            w for w in projection if int(w["week"]) <= 4 and float(w["projected_balance"]) < 0
        ]
        if not early_hist and not early_proj:
            mins = [f"history {p['week']}={p['balance']}" for p in history if int(p["week"]) <= 5]
            pmins = [
                f"projection {w['week']}={w['projected_balance']}"
                for w in projection
                if int(w["week"]) <= 4
            ]
            return [
                _fail(
                    "status",
                    "negative cash by history week 5 or projection week 4",
                    "; ".join(mins + pmins) or "no early points",
                    "cash_and_invoices.json",
                )
            ]
        return []
    if case.cash_shape == "critical_later":
        early = [p for p in history if int(p["week"]) <= 16 and float(p["balance"]) < 0]
        later = [p for p in history if int(p["week"]) >= 20 and float(p["balance"]) < 0]
        if early or not later:
            return [
                _fail(
                    "status",
                    "cash stays non-negative through history week 16 and is negative by week 20+",
                    "early negative weeks "
                    + ",".join(str(p["week"]) for p in early)
                    + "; later negative weeks "
                    + ",".join(str(p["week"]) for p in later),
                    "cash_and_invoices.json",
                )
            ]
    return []


def check_consistency(case: Case, data: dict[str, Any]) -> list[Failure]:
    monthly = data["monthly_reports.json"]
    cash = data["cash_and_invoices.json"]
    answer = data["answer_key.json"]
    months = monthly.get("months") or []
    failures: list[Failure] = []
    if len(months) < 2:
        return [
            _fail(
                "consistency", "at least 2 months", f"{len(months)} months", "monthly_reports.json"
            )
        ]
    for prev, cur in itertools.pairwise(months):
        expect = _month_add(str(prev["month"]))
        if str(cur["month"]) != expect:
            failures.append(
                _fail(
                    "consistency",
                    f"{prev['month']} followed by {expect}",
                    f"{prev['month']} followed by {cur['month']}",
                    "monthly_reports.json",
                )
            )
            break
    for row in months:
        assets = row["balance_sheet"]["assets"]
        el = row["balance_sheet"]["equity_and_liabilities"]
        asset_sum = (
            float(assets["fixed_assets"])
            + float(assets["inventory"])
            + float(assets["receivables"])
            + float(assets["cash"])
        )
        el_sum = (
            float(el["equity"])
            + float(el["loans"])
            + float(el["payables"])
            + float(el["other_current_liabilities"])
        )
        if (
            not _near(asset_sum, float(assets["total_assets"]))
            or not _near(el_sum, float(el["total_equity_and_liabilities"]))
            or not _near(float(assets["total_assets"]), float(el["total_equity_and_liabilities"]))
        ):
            failures.append(
                _fail(
                    "consistency",
                    f"{row['month']} assets equal equity+liabilities",
                    (
                        f"assets {assets['total_assets']} (lines {round(asset_sum, 2)}) "
                        f"equity+liabilities {el['total_equity_and_liabilities']} "
                        f"(lines {round(el_sum, 2)})"
                    ),
                    "monthly_reports.json",
                )
            )
            break
    last_cash = float(months[-1]["balance_sheet"]["assets"]["cash"])
    hist = cash.get("balance_history") or []
    if not hist or not _near(float(hist[-1]["balance"]), last_cash):
        got = None if not hist else hist[-1]["balance"]
        failures.append(
            _fail(
                "consistency",
                f"last history cash {last_cash}",
                f"last history cash {got}",
                "cash_and_invoices.json",
            )
        )
    hist_dates = [str(p["date"]) for p in hist]
    step = _dates_step(hist_dates, file="balance_history") if len(hist_dates) >= 2 else "no history"
    if step:
        failures.append(
            _fail("consistency", "history dates every 7 days", step, "cash_and_invoices.json")
        )
    proj = cash.get("projection_from_open_invoices") or []
    proj_dates = [str(w["week_end"]) for w in proj]
    pstep = _dates_step(proj_dates, file="projection") if len(proj_dates) >= 2 else "no projection"
    if pstep:
        failures.append(
            _fail(
                "consistency", "projection week ends every 7 days", pstep, "cash_and_invoices.json"
            )
        )
    chained = _chain_ok(proj, last_cash) if proj else "no projection"
    if chained:
        failures.append(
            _fail(
                "consistency",
                "projection balances chain from last monthly cash",
                chained,
                "cash_and_invoices.json",
            )
        )
    sales = _sum_invoices(cash, "sales")
    purchases = _sum_invoices(cash, "purchase")
    receivables = float(months[-1]["balance_sheet"]["assets"]["receivables"])
    payables = float(months[-1]["balance_sheet"]["equity_and_liabilities"]["payables"])
    key_totals = answer.get("invoice_totals") or {}
    key_sales = key_totals.get("open_sales_incl_vat_eur")
    key_purch = key_totals.get("open_purchases_incl_vat_eur")
    if key_sales is None or not _near(float(key_sales), sales):
        failures.append(
            _fail(
                "consistency",
                f"answer key open sales {sales}",
                f"answer key open sales {key_sales}",
                "answer_key.json",
            )
        )
    if key_purch is None or not _near(float(key_purch), purchases):
        failures.append(
            _fail(
                "consistency",
                f"answer key open purchases {purchases}",
                f"answer key open purchases {key_purch}",
                "answer_key.json",
            )
        )
    if case.broken_receivables:
        if _near(sales, receivables, tol=1.0):
            failures.append(
                _fail(
                    "consistency",
                    "open sales differ from receivables (invoices out of balance)",
                    f"open sales {sales} receivables {receivables}",
                    "cash_and_invoices.json",
                )
            )
    else:
        if not _near(sales, receivables):
            failures.append(
                _fail(
                    "consistency",
                    f"open sales {receivables}",
                    f"open sales {sales}",
                    "cash_and_invoices.json",
                )
            )
    if not _near(purchases, payables):
        failures.append(
            _fail(
                "consistency",
                f"open purchases {payables}",
                f"open purchases {purchases}",
                "cash_and_invoices.json",
            )
        )
    return failures


def _source_is(sources: dict[str, str], *keys: str, want: str) -> bool:
    for key in keys:
        if sources.get(key) == want:
            return True
    return False


def _value(params: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if params.get(key) is not None:
            return params.get(key)
    return None


def check_fidelity(case: Case, data: dict[str, Any]) -> list[Failure]:
    params = _params(data)
    sources = _sources(params)
    failures: list[Failure] = []
    stated = case.stated_values
    if "revenue_monthly_eur" in stated:
        got = _value(params, "monthly_revenue_start_eur", "revenue_monthly_eur")
        if got is None or not _near(float(got), stated["revenue_monthly_eur"], tol=0.02):
            failures.append(
                _fail(
                    "fidelity",
                    f"monthly revenue {stated['revenue_monthly_eur']}",
                    f"monthly revenue {got}",
                    "input.json",
                )
            )
        if not _source_is(
            sources, "monthly_revenue_start_eur", "revenue_monthly_eur", want="stated"
        ):
            failures.append(
                _fail(
                    "fidelity",
                    "monthly revenue source stated",
                    str(sources.get("monthly_revenue_start_eur")),
                    "input.json",
                )
            )
        annual = _value(params, "revenue_annual_eur")
        expect_annual = round(stated["revenue_monthly_eur"] * 12.0, 2)
        if annual is None or not _near(float(annual), expect_annual):
            failures.append(
                _fail(
                    "fidelity",
                    f"derived annual revenue {expect_annual}",
                    f"annual revenue {annual}",
                    "input.json",
                )
            )
    elif "revenue_annual_eur" in stated:
        annual = _value(params, "revenue_annual_eur")
        if annual is None or not _near(float(annual), stated["revenue_annual_eur"]):
            failures.append(
                _fail(
                    "fidelity",
                    f"annual revenue {stated['revenue_annual_eur']}",
                    f"annual revenue {annual}",
                    "input.json",
                )
            )
        if not _source_is(sources, "revenue_annual_eur", want="stated"):
            failures.append(
                _fail(
                    "fidelity",
                    "annual revenue source stated",
                    str(sources.get("revenue_annual_eur")),
                    "input.json",
                )
            )
        expect_monthly = round(stated["revenue_annual_eur"] / 12.0, 2)
        got = _value(params, "monthly_revenue_start_eur")
        if got is None or not _near(float(got), expect_monthly):
            failures.append(
                _fail(
                    "fidelity",
                    f"derived monthly revenue {expect_monthly}",
                    f"monthly revenue {got}",
                    "input.json",
                )
            )
        if not _source_is(
            sources, "monthly_revenue_start_eur", "revenue_monthly_eur", want="derived"
        ):
            failures.append(
                _fail(
                    "fidelity",
                    "monthly revenue source derived",
                    str(
                        sources.get("monthly_revenue_start_eur")
                        or sources.get("revenue_monthly_eur")
                    ),
                    "input.json",
                )
            )
    else:
        if _source_is(
            sources,
            "monthly_revenue_start_eur",
            "revenue_monthly_eur",
            "revenue_annual_eur",
            want="stated",
        ):
            failures.append(
                _fail(
                    "fidelity",
                    "revenue not stated",
                    "a revenue field is source stated",
                    "input.json",
                )
            )
    if "growth_per_month_percent" in stated:
        pct = _value(params, "growth_per_month_percent")
        frac = _value(params, "monthly_revenue_growth", "growth_per_month_fraction")
        if pct is None or abs(float(pct) - stated["growth_per_month_percent"]) > 1e-6:
            failures.append(
                _fail(
                    "fidelity",
                    f"growth percent {stated['growth_per_month_percent']}",
                    f"growth percent {pct}",
                    "input.json",
                )
            )
        expect_frac = stated["growth_per_month_percent"] / 100.0
        if frac is None or abs(float(frac) - expect_frac) > 1e-6:
            failures.append(
                _fail(
                    "fidelity",
                    f"derived growth fraction {expect_frac}",
                    f"growth fraction {frac}",
                    "input.json",
                )
            )
        if not _source_is(sources, "growth_per_month_percent", want="stated"):
            failures.append(
                _fail(
                    "fidelity",
                    "growth percent source stated",
                    str(sources.get("growth_per_month_percent")),
                    "input.json",
                )
            )
        if not _source_is(
            sources, "monthly_revenue_growth", "growth_per_month_fraction", want="derived"
        ):
            failures.append(
                _fail(
                    "fidelity",
                    "growth fraction source derived",
                    str(sources.get("monthly_revenue_growth")),
                    "input.json",
                )
            )
    elif _source_is(sources, "growth_per_month_percent", "monthly_revenue_growth", want="stated"):
        failures.append(
            _fail("fidelity", "growth not stated", "growth source stated", "input.json")
        )
    for stated_name, output_name in (
        ("starting_cash_eur", "starting_cash_eur"),
        ("covenant_min_cash_eur", "covenant_min_cash_eur"),
        ("dso_days", "days_sales_outstanding"),
        ("dpo_days", "days_payables_outstanding"),
    ):
        if stated_name in stated:
            got = _value(params, output_name, stated_name)
            if got is None or not _near(float(got), stated[stated_name], tol=0.02):
                failures.append(
                    _fail(
                        "fidelity",
                        f"{output_name} {stated[stated_name]}",
                        f"{output_name} {got}",
                        "input.json",
                    )
                )
            if not _source_is(sources, output_name, stated_name, want="stated"):
                failures.append(
                    _fail(
                        "fidelity",
                        f"{output_name} source stated",
                        str(sources.get(output_name)),
                        "input.json",
                    )
                )
        elif _source_is(sources, output_name, stated_name, want="stated"):
            failures.append(
                _fail(
                    "fidelity",
                    f"{stated_name} not stated",
                    f"{output_name} source stated",
                    "input.json",
                )
            )
    events = list(params.get("one_off_events") or [])
    if case.one_off:
        match = [
            ev
            for ev in events
            if _near(float(ev.get("amount_eur") or 0), float(case.one_off["amount_eur"]))
            and int(ev.get("month_index") or 0) == int(case.one_off["month_index"])
            and str(ev.get("direction")) == case.one_off["direction"]
        ]
        if not match:
            failures.append(
                _fail(
                    "fidelity",
                    (
                        f"one-off {case.one_off['direction']} "
                        f"{case.one_off['amount_eur']} in month {case.one_off['month_index']}"
                    ),
                    f"one_off_events {events}",
                    "input.json",
                )
            )
        if case.one_off["direction"] == "outflow":
            invest = _value(params, "special_investment_eur")
            month = _value(params, "special_investment_month")
            if invest is None or not _near(float(invest), float(case.one_off["amount_eur"])):
                failures.append(
                    _fail(
                        "fidelity",
                        f"outflow copied to special_investment {case.one_off['amount_eur']}",
                        f"special_investment_eur {invest}",
                        "input.json",
                    )
                )
            if month is None or int(month) != int(case.one_off["month_index"]):
                failures.append(
                    _fail(
                        "fidelity",
                        f"special_investment_month {case.one_off['month_index']}",
                        f"special_investment_month {month}",
                        "input.json",
                    )
                )
        else:
            invest = float(params.get("special_investment_eur") or 0.0)
            if invest > 0.02:
                failures.append(
                    _fail(
                        "fidelity",
                        "inflow is not recorded as a capex outflow",
                        f"special_investment_eur {invest}",
                        "input.json",
                    )
                )
    else:
        if events:
            failures.append(
                _fail("fidelity", "no one-off events", f"one_off_events {events}", "input.json")
            )
        invest = float(params.get("special_investment_eur") or 0.0)
        if invest > 0.02:
            failures.append(
                _fail(
                    "fidelity",
                    "special_investment_eur 0",
                    f"special_investment_eur {invest}",
                    "input.json",
                )
            )
    return failures


def _month1_revenue(data: dict[str, Any]) -> float:
    return float(data["monthly_reports.json"]["months"][0]["income_statement"]["revenue"])


def _expected_monthly(case: Case, params: dict[str, Any]) -> float | None:
    if "revenue_monthly_eur" in case.stated_values:
        return float(case.stated_values["revenue_monthly_eur"])
    if "revenue_annual_eur" in case.stated_values:
        return round(float(case.stated_values["revenue_annual_eur"]) / 12.0, 2)
    got = params.get("monthly_revenue_start_eur")
    return None if got is None else float(got)


def _projection_opening(cash: dict[str, Any], latest_cash: float) -> float:
    """Opening cash of the open-invoice projection (latest cash before week flows)."""
    weeks = cash.get("projection_from_open_invoices") or []
    if not weeks:
        return latest_cash
    week = weeks[0]
    return round(
        float(week["projected_balance"])
        - float(week["sales_inflow"])
        + float(week["purchase_outflow"]),
        2,
    )


def _assumed_starting_cash_moves(case: Case, data: dict[str, Any]) -> list[Failure]:
    """Change an assumed opening. Latest cash and the projection opening must follow."""
    params = _params(data)
    sources = _sources(params)
    if sources.get("starting_cash_eur") == "stated":
        return [
            _fail(
                "sensitivity",
                "starting cash source assumed",
                "starting cash source stated",
                "input.json",
            )
        ]
    start = params.get("starting_cash_eur")
    if start is None:
        return [
            _fail(
                "sensitivity",
                "an assumed starting cash",
                "starting_cash_eur missing",
                "input.json",
            )
        ]
    from payloq_generator.engine import generate_pack
    from payloq_schemas.models import GeneratorInput

    base_in = GeneratorInput.model_validate(data["input.json"])
    bumped = round(float(start) * 1.25 + 1000.0, 2)
    alt_params = base_in.parameters_from_language_model.model_copy(
        update={"starting_cash_eur": bumped}
    )
    alt_in = base_in.model_copy(update={"parameters_from_language_model": alt_params})
    alt = generate_pack(alt_in, seed=case.seed)
    base_latest = float(
        data["monthly_reports.json"]["months"][-1]["balance_sheet"]["assets"]["cash"]
    )
    alt_latest = float(alt.monthly_reports.months[-1].balance_sheet.assets.cash)
    base_open = _projection_opening(data["cash_and_invoices.json"], base_latest)
    alt_week = alt.cash_and_invoices.projection_from_open_invoices[0]
    alt_open = round(
        float(alt_week.projected_balance)
        - float(alt_week.sales_inflow)
        + float(alt_week.purchase_outflow),
        2,
    )
    failures: list[Failure] = []
    if not alt_latest > base_latest + 1.0:
        failures.append(
            _fail(
                "sensitivity",
                f"latest cash moves up when assumed starting cash rises from {start} to {bumped}",
                f"latest cash {base_latest} -> {alt_latest}",
                "monthly_reports.json",
            )
        )
    if not alt_open > base_open + 1.0:
        failures.append(
            _fail(
                "sensitivity",
                f"projection opening moves up when assumed starting cash rises from {start} to {bumped}",
                f"projection opening {base_open} -> {alt_open}",
                "cash_and_invoices.json",
            )
        )
    return failures


def check_sensitivity(case: Case, data: dict[str, Any], templates: dict[str, Any]) -> list[Failure]:
    params = _params(data)
    failures: list[Failure] = []
    target = _expected_monthly(case, params)
    if target is None:
        return [_fail("sensitivity", "a monthly revenue figure", "missing", "input.json")]
    month1 = _month1_revenue(data)
    if not _band(month1, target):
        failures.append(
            _fail(
                "sensitivity",
                f"month-1 revenue within {NOISE:.1%} of {target}",
                f"month-1 revenue {month1}",
                "monthly_reports.json",
            )
        )
    if "starting_cash_eur" not in case.stated_values:
        failures.extend(_assumed_starting_cash_moves(case, data))
    if (
        "revenue_monthly_eur" not in case.stated_values
        and "revenue_annual_eur" not in case.stated_values
    ):
        from payloq_schemas.industry_defaults import draw_assumed_defaults

        drawn = draw_assumed_defaults(
            industry=case.industry,
            company_size=case.company_size,
            seed=case.seed,
            description=case.text,
        )
        expect = float(drawn["monthly_revenue_start_eur"])
        got = params.get("monthly_revenue_start_eur")
        if got is None or not _near(float(got), expect):
            failures.append(
                _fail(
                    "sensitivity",
                    f"unstated revenue follows seed draw {expect}",
                    f"monthly_revenue_start_eur {got}",
                    "input.json",
                )
            )
    other_seed = next(seed for seed in SEEDS if seed != case.seed)
    other = build_case(case.scenario, other_seed, templates)
    if "revenue_monthly_eur" in case.stated_values and "revenue_monthly_eur" in other.stated_values:
        this_v = float(case.stated_values["revenue_monthly_eur"])
        other_v = float(other.stated_values["revenue_monthly_eur"])
        if (
            abs(this_v - other_v) / max(this_v, 1.0) > 0.05
            and _band(month1, other_v)
            and not _band(month1, this_v)
        ):
            failures.append(
                _fail(
                    "sensitivity",
                    f"month-1 revenue tracks this seed {this_v}, not seed {other_seed} {other_v}",
                    f"month-1 revenue {month1}",
                    "monthly_reports.json",
                )
            )
    return failures


def check_repeatability(out_a: Path, out_b: Path) -> list[Failure]:
    failures: list[Failure] = []
    for name in FILES:
        ha = _sha(out_a / name)
        hb = _sha(out_b / name)
        if ha is None or hb is None or ha != hb:
            failures.append(
                _fail(
                    "repeatability",
                    f"{name} sha256 identical across two runs",
                    f"run A {ha} run B {hb}",
                    name,
                )
            )
    return failures


def check_seed_isolation(
    case: Case, data: dict[str, Any], templates: dict[str, Any]
) -> list[Failure]:
    failures: list[Failure] = []
    params = _params(data)
    input_seed = (data["input.json"].get("meta") or {}).get("seed")
    month_seed = (data["monthly_reports.json"].get("meta") or {}).get("seed")
    cash_seed = (data["cash_and_invoices.json"].get("meta") or {}).get("seed")
    extraction_seed = params.get("extraction_seed")
    for label, got, file in (
        ("input.meta.seed", input_seed, "input.json"),
        ("monthly_reports.meta.seed", month_seed, "monthly_reports.json"),
        ("cash_and_invoices.meta.seed", cash_seed, "cash_and_invoices.json"),
        ("extraction_seed", extraction_seed, "input.json"),
    ):
        if got is None or int(got) != int(case.seed):
            failures.append(_fail("seed isolation", f"{label} {case.seed}", f"{label} {got}", file))
    other_seed = next(seed for seed in SEEDS if seed != case.seed)
    other = build_case(case.scenario, other_seed, templates)
    if "revenue_monthly_eur" in case.stated_values and "revenue_monthly_eur" in other.stated_values:
        this_v = float(case.stated_values["revenue_monthly_eur"])
        other_v = float(other.stated_values["revenue_monthly_eur"])
        got = _value(params, "monthly_revenue_start_eur")
        if (
            got is not None
            and abs(this_v - other_v) > 1.0
            and _near(float(got), other_v)
            and not _near(float(got), this_v)
        ):
            failures.append(
                _fail(
                    "seed isolation",
                    f"stored revenue is this seed {this_v}",
                    f"stored revenue {got} matches seed {other_seed}",
                    "input.json",
                )
            )
    return failures


def evaluate_case(
    case: Case,
    out_a: Path,
    out_b: Path,
    *,
    call_error: str | None,
    templates: dict[str, Any],
) -> list[Failure]:
    failures = check_status(case, out_a, call_error)
    data, missing = _load(out_a)
    if missing or data is None:
        # Status already names the missing files. Repeatability is reported only
        # when one run wrote files and the other did not.
        if any((out_a / name).is_file() or (out_b / name).is_file() for name in FILES):
            failures.extend(check_repeatability(out_a, out_b))
        return failures
    failures.extend(check_consistency(case, data))
    failures.extend(check_fidelity(case, data))
    failures.extend(check_sensitivity(case, data, templates))
    failures.extend(check_repeatability(out_a, out_b))
    failures.extend(check_seed_isolation(case, data, templates))
    return failures

"""Run #57 work-order gaps: profitable cash_critical + history scale + paste cleanup."""

from __future__ import annotations

from payloq_generator.engine import generate_pack
from payloq_llm.text_sanitize import normalize_scenario_description
from payloq_schemas.constants import PROJECTION_HISTORY_SCALE_RATIO
from payloq_schemas.models import (
    CostShares,
    GeneratorInput,
    OneOffCashEvent,
    Options,
    ParametersFromLanguageModel,
    ScenarioDescription,
    ScenarioMeta,
)
from payloq_api.services.model_compare import resolve_judge_model
from payloq_validate.checks import validate_pack


def _run57_input() -> GeneratorInput:
    params = ParametersFromLanguageModel(
        monthly_revenue_start_eur=210_000.0,
        monthly_revenue_growth=0.002427,
        cost_shares_of_revenue=CostShares(
            materials=0.37, services=0.08, personnel=0.34, other=0.15
        ),
        days_sales_outstanding=30.0,
        days_payables_outstanding=37.0,
        starting_cash_eur=65_000.0,
        target_cash_at_end_eur=40_000.0,
        covenant_min_cash_eur=50_000.0,
        scenario_shape="cash_critical",
        one_off_events=[
            OneOffCashEvent(
                amount_eur=95_000.0, month_index=5, direction="outflow", label="equipment"
            )
        ],
        field_sources={
            "monthly_revenue_start_eur": "stated",
            "starting_cash_eur": "stated",
            "covenant_min_cash_eur": "stated",
            "one_off_events": "stated",
            "cost_shares_of_revenue": "assumed",
            "days_sales_outstanding": "assumed",
            "days_payables_outstanding": "assumed",
            "monthly_revenue_growth": "assumed",
        },
    )
    # Calibrate assumed costs the same way assume.py does for cash_critical.
    from payloq_schemas.industry_defaults import calibrate_cost_shares_for_shape

    calibrated = calibrate_cost_shares_for_shape(
        params.cost_shares_of_revenue.model_dump(),
        start_revenue_eur=210_000.0,
        scenario_shape="cash_critical",
    )
    params = params.model_copy(
        update={"cost_shares_of_revenue": CostShares(**calibrated)}
    )
    return GeneratorInput(
        meta=ScenarioMeta(scenario="cash_critical", fictional=True, currency="EUR"),
        options=Options(
            industry="unspecified",
            company_size="small",
            scenario_id="cash_critical",
            months=12,
            language="en",
            as_of="2026-10-31",
        ),
        scenario_description=ScenarioDescription(
            en=(
                "Monthly revenue 210,000 euro. Starting cash 65,000 euro. "
                "Bank minimum cash 50,000 euro. One-off equipment outflow of "
                "95,000 euro in month 5."
            ),
            fi="",
        ),
        parameters_from_language_model=params,
    )


def test_normalize_strips_leading_enumeration() -> None:
    raw = (
        "2. Monthly revenue 210,000 euro. Starting cash 65,000 euro. "
        "Bank minimum cash 50,000 euro."
    )
    assert normalize_scenario_description(raw).startswith("Monthly revenue")


def test_resolve_judge_never_equals_pack() -> None:
    assert (
        resolve_judge_model(
            pulled=["qwen2.5:7b", "llama3.2:3b", "qwen2.5:3b"],
            pack_model="qwen2.5:7b",
        )
        == "llama3.2:3b"
    )
    assert (
        resolve_judge_model(pulled=["qwen2.5:7b"], pack_model="qwen2.5:7b") is None
    )


def test_run57_cash_critical_is_profitable_with_history_scale() -> None:
    pack = generate_pack(_run57_input(), seed=42)
    nets = [m.income_statement.net_result for m in pack.monthly_reports.months]
    assert sum(nets) > 0, "cash_critical must not assume a loss-making P&L"

    hist = pack.cash_and_invoices.balance_history
    proj = pack.cash_and_invoices.projection_from_open_invoices
    hist_moves = [
        abs(hist[i].balance - hist[i - 1].balance) for i in range(1, len(hist))
    ]
    proj_moves = [
        abs(float(w.sales_inflow) + float(w.purchase_outflow)) for w in proj
    ]
    max_hist = max(hist_moves) if hist_moves else 0.0
    max_proj = max(proj_moves) if proj_moves else 0.0
    assert max_hist > 5_000.0, "history must show supplier-scale week moves"
    assert max_proj <= PROJECTION_HISTORY_SCALE_RATIO * max_hist * 1.05

    result = validate_pack(pack)
    scale = [i for i in result.issues if i.code == "projection_history_scale"]
    assert not scale, f"unexpected VR-08 scale warning: {scale}"
    # Timing cliff still required somewhere (projection or history).
    neg = [w for w in proj if w.projected_balance < 0] or [
        p for p in hist if p.balance < 0
    ]
    assert neg, "cash_critical must still show negative cash from timing"

"""Anmol scoring feedback: FR-A-11 cost shares, seasonality, one-offs, VR-22, naming."""

from __future__ import annotations

import json
from pathlib import Path

from payloq_generator.engine import generate_pack
from payloq_generator.params_clamp import clamp_parameters, cost_share_sum
from payloq_generator.pipeline import run_generation
from payloq_schemas.models import CostShares, ParametersFromLanguageModel
from payloq_schemas.text_rules import descriptive_text_has_numbers
from payloq_validate.checks import validate_pack

from helpers_stub_input import generator_input_via_stub_extract

ROOT = Path(__file__).resolve().parents[1]

HOTEL_WINTER_NL = (
    "A 12-room boutique hotel near the harbour; occupancy around 65% with "
    "ADR ~€180 in summer. Bookings collapse Oct–Mar (winter off-season ~0.3×). "
    "Capex: €95,000 roof repair in month 2. Cash tight and critical within weeks "
    "after a €25k supplier bill cluster. Still aiming for a profitable year on paper."
)


def test_cost_share_sum_1_90_repaired_and_logged() -> None:
    params = ParametersFromLanguageModel(
        monthly_revenue_start_eur=200_000,
        monthly_revenue_growth=0.0,
        cost_shares_of_revenue=CostShares(
            materials=0.50,
            services=0.50,
            personnel=0.50,
            other=0.40,
        ),
        days_sales_outstanding=40,
        days_payables_outstanding=30,
        target_cash_at_end_eur=50_000,
    )
    assert abs(cost_share_sum(params.cost_shares_of_revenue.model_dump()) - 1.90) < 1e-9
    clamped, changes = clamp_parameters(params)
    new_sum = cost_share_sum(clamped.cost_shares_of_revenue.model_dump())
    assert 0.9 - 1e-6 <= new_sum <= 1.0 + 1e-6
    assert any(
        c.get("field") == "cost_shares_of_revenue" and "1.9" in str(c.get("original_sum", c.get("message")))
        for c in changes
    )


def test_cost_share_repair_lands_in_run_log(tmp_path: Path) -> None:
    from payloq_generator.engine import load_input

    inp = load_input(ROOT / "scenarios" / "good" / "input.json")
    bad = inp.parameters_from_language_model.model_copy(
        update={
            "cost_shares_of_revenue": CostShares(
                materials=0.55,
                services=0.45,
                personnel=0.50,
                other=0.40,
            )
        }
    )
    inp = inp.model_copy(update={"parameters_from_language_model": bad})
    outcome = run_generation(inp, tmp_path / "shares", seed=42)
    assert outcome.ok, outcome.validation.issues
    assert outcome.param_clips
    run_log = json.loads((outcome.out_dir / "run_log.json").read_text(encoding="utf-8"))
    assert run_log["parameter_clips"]
    assert any("cost_shares" in str(c.get("field")) for c in run_log["parameter_clips"])
    shares = outcome.pack.input.parameters_from_language_model.cost_shares_of_revenue
    assert 0.9 <= cost_share_sum(shares.model_dump()) <= 1.0


def test_hotel_winter_seasonality_and_month2_investment(tmp_path: Path) -> None:
    inp = generator_input_via_stub_extract(
        text=HOTEL_WINTER_NL,
        language="en",
        options={
            "industry": "boutique hotel",
            "company_size": "small",
            "months": 12,
            "language": "en",
            "currency": "EUR",
            "as_of": "2026-10-31",
        },
    )
    params = inp.parameters_from_language_model
    assert params.monthly_revenue_factors is not None
    assert len(params.monthly_revenue_factors) == 12
    # Winter Oct–Mar should be low vs summer
    assert params.monthly_revenue_factors[0] < 0.5  # Jan
    assert params.monthly_revenue_factors[6] >= 0.9  # Jul
    assert params.special_investment_eur >= 95_000
    assert params.special_investment_month == 2

    outcome = run_generation(inp, tmp_path / "hotel", seed=42, llm_name="stub")
    assert outcome.pack is not None
    pack = outcome.pack

    # Cost shares valid after clamp
    shares = pack.input.parameters_from_language_model.cost_shares_of_revenue
    assert 0.9 <= cost_share_sum(shares.model_dump()) <= 1.0

    # Seasonality applied: a winter month revenue << a summer month (same growth≈0)
    months = pack.monthly_reports.months
    by_cal = {int(m.month.split("-")[1]): m.income_statement.revenue for m in months}
    # Pack ends Oct 2026 → includes Jul and Jan (or Feb) of the horizon
    summer_revs = [by_cal[m] for m in (6, 7, 8) if m in by_cal]
    winter_revs = [by_cal[m] for m in (1, 2, 11, 12) if m in by_cal]
    assert summer_revs and winter_revs
    assert min(summer_revs) > max(winter_revs) * 1.5

    # Month 2 (second monthly report): FA rises by ~investment (capex)
    m1_fa = months[0].balance_sheet.assets.fixed_assets
    m2_fa = months[1].balance_sheet.assets.fixed_assets
    invest = pack.input.parameters_from_language_model.special_investment_eur
    assert m2_fa - m1_fa > invest * 0.5  # net of depreciation

    # Applied event logged + visible in run_log
    run_log = json.loads((outcome.out_dir / "run_log.json").read_text(encoding="utf-8"))
    applied = run_log.get("one_off_events_applied") or []
    assert any(int(e.get("month_index", 0)) == 2 for e in applied)

    # Weekly history shows a large outflow (~investment)
    hist = pack.cash_and_invoices.balance_history
    week_drops = [
        hist[i].balance - hist[i - 1].balance for i in range(1, len(hist))
    ]
    assert any(d <= -invest * 0.8 for d in week_drops), week_drops

    # VR-13 clean
    vr13 = [
        i
        for i in outcome.validation.issues
        if i.severity == "error" and (i.rule_id == "VR-13" or i.code == "text_has_numbers")
    ]
    assert not vr13, vr13
    for inv in pack.cash_and_invoices.open_invoices:
        assert not descriptive_text_has_numbers(inv.counterparty)
        assert not descriptive_text_has_numbers(inv.description)

    # Cash-critical intent: negative cash somewhere (VR-20)
    neg_proj = [w for w in pack.cash_and_invoices.projection_from_open_invoices if w.projected_balance < 0]
    neg_hist = [p for p in hist if p.balance < 0]
    assert neg_proj or neg_hist

    # Custom hotel must not be mislabelled cash_critical.xlsx
    sid = pack.input.options.scenario_id or ""
    assert sid != "cash_critical"
    assert "hotel" in sid.lower() or sid.startswith("boutique")
    assert (outcome.out_dir / f"scenario_{sid}.xlsx").exists()
    assert not (outcome.out_dir / "scenario_cash_critical.xlsx").exists()


def test_ending_cash_via_dynamics_not_forced_exact() -> None:
    from payloq_generator.engine import load_input

    inp = load_input(ROOT / "scenarios" / "cash_critical" / "input.json")
    pack = generate_pack(inp, seed=42)
    target = pack.input.parameters_from_language_model.target_cash_at_end_eur
    end = pack.monthly_reports.months[-1].balance_sheet.assets.cash
    # Near target via dynamics — not forced bitwise equality
    assert abs(end - target) < 5_000, (end, target)
    # Exact equality is not required (artificial snap removed)
    meta = getattr(pack, "_generator_meta", {}) or {}
    assert meta.get("ending_cash_note")
    assert "via_dynamics" in str(meta.get("ending_cash_note"))


def test_vr22_pnl_is_not_vr20_error() -> None:
    from payloq_generator.engine import load_input

    inp = load_input(ROOT / "scenarios" / "cash_critical" / "input.json")
    params = inp.parameters_from_language_model.model_copy(
        update={
            "cost_shares_of_revenue": CostShares(
                materials=0.45,
                services=0.15,
                personnel=0.40,
                other=0.20,
            ),
            "monthly_revenue_growth": -0.02,
            "partly_fixed_costs": True,
        }
    )
    # Repair shares first so generation uses valid shares but still unprofitable
    clamped, _ = clamp_parameters(params)
    inp = inp.model_copy(update={"parameters_from_language_model": clamped})
    pack = generate_pack(inp, seed=42)
    # Force scenario id for behaviour check
    pack.input.options.scenario_id = "cash_critical"
    result = validate_pack(pack)
    hard_pnl = [
        i
        for i in result.issues
        if i.code == "behaviour_cash_critical_pnl" and i.severity == "error"
    ]
    assert not hard_pnl
    # Negative cash remains the VR-20 signal
    neg = any(w.projected_balance < 0 for w in pack.cash_and_invoices.projection_from_open_invoices) or any(
        p.balance < 0 for p in pack.cash_and_invoices.balance_history
    )
    assert neg

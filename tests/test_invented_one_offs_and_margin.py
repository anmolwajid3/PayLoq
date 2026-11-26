"""Generic rules: ungrounded one-offs are rejected; healthy profiles are profitable by construction."""

from __future__ import annotations

import random

import pytest

from payloq_llm.extract_pipeline import finalize_extracted_parameters
from payloq_llm.stated_checks import reject_ungrounded_one_offs
from payloq_schemas.constants import (
    COST_SHARE_SUM_MAX,
    COST_SHARE_SUM_MIN,
    FIXED_DEPRECIATION_MONTHLY_EUR,
    INTEREST_ANNUAL_RATE,
    LOAN_ANCHOR_EUR,
)
from payloq_schemas.industry_defaults import (
    calibrate_cost_shares_for_shape,
    healthy_variable_cost_sum,
)

STATED_INFLOW = "One-off inflow of 40,000 euro in month 2."
NO_ONE_OFF = "Monthly revenue 210,000 euro. Bank minimum cash 50,000 euro."


def _ev(amount: float, month: int, direction: str = "inflow") -> dict:
    return {"type": "other", "amount_eur": amount, "month_index": month, "direction": direction}


@pytest.mark.parametrize("seed", range(20))
def test_stated_one_off_is_grounded(seed: random.Random) -> None:
    rng = random.Random(seed)
    amount = rng.randrange(10, 300) * 1000
    month = rng.randrange(1, 12)
    text = f"Monthly revenue 210,000 euro. One-off inflow of {amount:,} euro in month {month}."
    assert reject_ungrounded_one_offs([_ev(amount, month)], text) == []


@pytest.mark.parametrize("seed", range(20))
def test_covenant_turned_into_inflow_is_rejected(seed: random.Random) -> None:
    rng = random.Random(seed)
    covenant = rng.randrange(20, 90) * 1000
    text = f"Monthly revenue 210,000 euro. Bank minimum cash {covenant:,} euro."
    issues = reject_ungrounded_one_offs([_ev(covenant, 3)], text)
    assert issues, "a covenant value must not become a one-off"


def test_description_without_one_off_accepts_none() -> None:
    assert reject_ungrounded_one_offs([_ev(179000, 1)], NO_ONE_OFF)


def test_wrong_month_or_direction_is_rejected() -> None:
    assert reject_ungrounded_one_offs([_ev(40000, 5)], STATED_INFLOW)
    assert reject_ungrounded_one_offs([_ev(40000, 2, "outflow")], STATED_INFLOW)
    assert reject_ungrounded_one_offs([_ev(40000, 2)], STATED_INFLOW) == []


def test_finalize_drops_revenue_mistyped_as_one_off_run59() -> None:
    """Run #59: qwen mistyped monthly revenue as a one-off inflow — drop, do not abort."""
    desc = (
        "Monthly revenue 1,200,000 euro. Growth 0.5% per month. "
        "Starting cash 800,000 euro. DSO 35 days. DPO 40 days."
    )
    envelope = {
        "scenario_shape": "unspecified",
        "scenario_shape_quote": None,
        "stated": {
            "revenue_monthly_eur": "Monthly revenue 1,200,000 euro",
            "growth_per_month_fraction": "Growth 0.5% per month",
            "starting_cash_eur": "Starting cash 800,000 euro",
            "dso_days": "DSO 35 days",
            "dpo_days": "DPO 40 days",
        },
        "parameters": {
            "revenue_monthly_eur": 1_200_000,
            "starting_cash_eur": 800_000,
            "growth_per_month_fraction": 0.005,
            "dso_days": 35,
            "dpo_days": 40,
            "one_off_events": [_ev(1_200_000, 1, "inflow")],
            "industry": None,
            "company_size": None,
        },
    }
    params, _changes, check = finalize_extracted_parameters(
        envelope,
        desc,
        industry="unspecified",
        company_size="medium",
        seed=42,
        months=12,
    )
    assert check.ok, check.error_text()
    assert params.get("one_off_events") in ([], None) or params["one_off_events"] == []
    assert any("dropped invented" in w for w in check.warnings)


@pytest.mark.parametrize("revenue", [80_000.0, 100_000.0, 150_000.0, 250_000.0])
def test_healthy_calibration_stays_in_fr_a_11_band(revenue: float) -> None:
    shares = {"materials": 0.37, "services": 0.08, "personnel": 0.34, "other": 0.15}
    out = calibrate_cost_shares_for_shape(shares, start_revenue_eur=revenue, scenario_shape="healthy")
    total = sum(out.values())
    assert COST_SHARE_SUM_MIN - 1e-6 <= total <= COST_SHARE_SUM_MAX + 1e-6


@pytest.mark.parametrize("revenue", [100_000.0, 150_000.0, 250_000.0])
def test_healthy_profile_keeps_margin_after_fixed_charges(revenue: float) -> None:
    fixed_ratio = (
        FIXED_DEPRECIATION_MONTHLY_EUR + LOAN_ANCHOR_EUR * INTEREST_ANNUAL_RATE / 12
    ) / revenue
    margin = 1.0 - healthy_variable_cost_sum(revenue) - fixed_ratio
    assert margin > 0.0


def test_loss_shapes_use_loss_cost_sum_and_unspecified_is_unchanged() -> None:
    shares = {"materials": 0.37, "services": 0.08, "personnel": 0.34, "other": 0.15}
    for shape in ("weak", "cash_tight"):
        out = calibrate_cost_shares_for_shape(shares, start_revenue_eur=100_000.0, scenario_shape=shape)
        assert abs(sum(out.values()) - 0.99) < 1e-4
    assert calibrate_cost_shares_for_shape(
        shares, start_revenue_eur=100_000.0, scenario_shape="unspecified"
    ) == shares


def test_cash_critical_assumed_costs_are_profitable_like_healthy() -> None:
    shares = {"materials": 0.37, "services": 0.08, "personnel": 0.34, "other": 0.15}
    revenue = 210_000.0
    critical = calibrate_cost_shares_for_shape(
        shares, start_revenue_eur=revenue, scenario_shape="cash_critical"
    )
    healthy = calibrate_cost_shares_for_shape(
        shares, start_revenue_eur=revenue, scenario_shape="healthy"
    )
    assert abs(sum(critical.values()) - sum(healthy.values())) < 1e-6
    assert sum(critical.values()) < 0.99

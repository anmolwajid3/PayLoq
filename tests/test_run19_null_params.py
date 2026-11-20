"""Run #19: null unstated ExtractedParameters + stub CAPEX €80k month 3."""

from __future__ import annotations

import pytest

from payloq_llm.adapters import StubLlmAdapter
from payloq_llm.assume import apply_assumed_defaults, drop_incomplete_one_off_events
from payloq_llm.extract_pipeline import finalize_extracted_parameters
from payloq_llm.nl_param_hints import extract_special_investment
from payloq_schemas.models import ExtractedParameters

RUN19_DESC = (
    "Monthly revenue €180,000. Growth 0.5% per month. Starting cash €45,000. "
    "Bank covenant minimum cash €40,000. DSO 35 days. DPO 28 days. "
    "One-off CAPEX €80,000 outflow in month 3."
)

# Ollama-shaped payload: null cost shares + incomplete one-off (Run #19).
RUN19_RAW = {
    "monthly_revenue_start_eur": 180_000,
    "monthly_revenue_growth": 0.005,
    "cost_shares_of_revenue": {
        "materials": None,
        "services": None,
        "personnel": None,
        "other": None,
    },
    "days_sales_outstanding": 35,
    "days_payables_outstanding": 28,
    "target_cash_at_end_eur": 40_000,
    "starting_cash_eur": 45_000,
    "covenant_min_cash_eur": 40_000,
    "special_investment_eur": None,
    "special_investment_month": None,
    "one_off_events": [
        {
            "type": "capex",
            "amount_eur": None,
            "month_index": None,
            "direction": "outflow",
        }
    ],
    "notes": "run19 extract with nulls",
    "partly_fixed_costs": None,
}


def test_extracted_parameters_accepts_null_cost_shares_and_partial_event() -> None:
    """Pydantic must allow null nested numerics (no ValidationError → stub fallback)."""
    extracted = ExtractedParameters.model_validate(RUN19_RAW)
    dumped = extracted.model_dump()
    shares = dumped["cost_shares_of_revenue"]
    assert shares is not None
    assert shares["materials"] is None
    assert shares["services"] is None
    assert shares["personnel"] is None
    assert shares["other"] is None
    assert dumped["one_off_events"][0]["amount_eur"] is None
    assert dumped["one_off_events"][0]["month_index"] is None


def test_drop_incomplete_one_off_events() -> None:
    cleaned, changes = drop_incomplete_one_off_events(RUN19_RAW["one_off_events"])
    assert cleaned == []
    assert any("incomplete" in (c.get("message") or "") for c in changes)


def test_null_cost_shares_and_partial_event_assumed() -> None:
    """Null shares → industry×size assumed; incomplete CAPEX row dropped."""
    extracted = ExtractedParameters.model_validate(RUN19_RAW).model_dump()
    filled, changes = apply_assumed_defaults(
        extracted,
        industry="other",
        company_size="small",
        seed=19,
        description=RUN19_DESC,
        require_starting_cash=True,
    )
    shares = filled["cost_shares_of_revenue"]
    assert all(isinstance(shares[k], float) for k in ("materials", "services", "personnel", "other"))
    sources = filled["field_sources"]
    assert sources.get("cost_shares_of_revenue") == "assumed"
    assert sources.get("cost_shares_of_revenue.materials") == "assumed"
    assert filled["one_off_events"] == []
    assert any("cost_shares" in (c.get("field") or "") for c in changes)
    assert any("one_off" in (c.get("field") or "") for c in changes)
    # Required stated fields preserved
    assert filled["starting_cash_eur"] == pytest.approx(45_000)
    assert filled["days_sales_outstanding"] == pytest.approx(35)
    assert filled["days_payables_outstanding"] == pytest.approx(28)
    assert filled["monthly_revenue_growth"] == pytest.approx(0.005)


def test_finalize_run19_null_payload_grounds_and_assumes() -> None:
    """Incomplete one-offs are dropped; null cost shares assumed; stated scalars kept."""
    envelope = {
        "scenario_shape": "unspecified",
        "scenario_shape_quote": None,
        "stated": {
            "revenue_monthly_eur": "Monthly revenue €180,000",
            "starting_cash_eur": "Starting cash €45,000",
            "covenant_min_cash_eur": "Bank covenant minimum cash €40,000",
            "dso_days": "DSO 35 days",
            "dpo_days": "DPO 28 days",
            "growth_per_month_fraction": "Growth 0.5% per month",
        },
        "parameters": {
            "revenue_monthly_eur": 180_000,
            "revenue_annual_eur": None,
            "growth_per_month_fraction": 0.005,
            "starting_cash_eur": 45_000,
            "covenant_min_cash_eur": 40_000,
            "dso_days": 35,
            "dpo_days": 28,
            "one_off_events": [
                {
                    "type": "capex",
                    "amount_eur": None,
                    "month_index": None,
                    "direction": None,
                }
            ],
            "industry": None,
            "company_size": None,
        },
    }
    params, changes, grounding = finalize_extracted_parameters(
        envelope,
        RUN19_DESC,
        industry="services",
        company_size="small",
        seed=19,
        require_starting_cash=False,
    )
    assert grounding.ok, grounding.error_text()
    assert params["monthly_revenue_start_eur"] == pytest.approx(180_000)
    assert params["starting_cash_eur"] == pytest.approx(45_000)
    assert params["target_cash_at_end_eur"] == pytest.approx(40_000)
    assert params["field_sources"].get("cost_shares_of_revenue") == "assumed"
    # Incomplete CAPEX dropped — investment assumed (not invented from NL keywords).
    assert params["one_off_events"] == []
    assert params["field_sources"].get("special_investment_eur") == "assumed"
    assert any("assumed" in (c.get("message") or "") for c in changes)


def test_complete_capex_event_promoted_before_assume() -> None:
    raw = dict(RUN19_RAW)
    raw["one_off_events"] = [
        {"type": "capex", "amount_eur": 80_000, "month_index": 3, "direction": "outflow"}
    ]
    params, _changes, grounding = finalize_extracted_parameters(
        raw,
        RUN19_DESC,
        industry="services",
        company_size="small",
        seed=19,
        require_starting_cash=True,
    )
    assert grounding.ok, grounding.error_text()
    assert params["special_investment_eur"] == pytest.approx(80_000)
    assert params["special_investment_month"] == 3
    assert params["field_sources"].get("special_investment_eur") == "stated"
    assert params["one_off_events"][0]["amount_eur"] == pytest.approx(80_000)


def test_extract_special_investment_prefers_capex_over_revenue() -> None:
    """FI+EN concat must not let €180k revenue steal CAPEX €80k month 3."""
    single = extract_special_investment(RUN19_DESC)
    doubled = extract_special_investment(f"{RUN19_DESC} {RUN19_DESC}")
    assert single == (80_000.0, 3)
    assert doubled == (80_000.0, 3)


def test_stub_run19_invest_80000_month_3() -> None:
    """Stub path: stated CAPEX €80k month 3 — do not invent €180k invest."""
    stub = StubLlmAdapter()
    out = stub.extract_parameters(
        RUN19_DESC,
        RUN19_DESC,
        {
            "industry": "other",
            "company_size": "small",
            "scenario_id": "custom",
            "language": "en",
        },
    )
    assert out["special_investment_eur"] == pytest.approx(80_000)
    assert out["special_investment_month"] == 3
    assert out["special_investment_eur"] != pytest.approx(180_000)
    events = out.get("one_off_events") or []
    assert events, "expected CAPEX one-off event"
    assert events[0]["amount_eur"] == pytest.approx(80_000)
    assert events[0]["month_index"] == 3
    assert events[0]["direction"] == "outflow"
    assert out["monthly_revenue_start_eur"] == pytest.approx(180_000)
    # Starting cash €45,000 is stated in NL (not covenant €40k).
    assert out["starting_cash_eur"] == pytest.approx(45_000)
    assert out["field_sources"].get("starting_cash_eur") == "stated"

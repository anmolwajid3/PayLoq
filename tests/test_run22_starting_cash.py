"""Run #22: starting_cash may be stated or assumed — never a hard fail (pilot fix §D/G)."""

from __future__ import annotations

import pytest

from payloq_llm.assume import apply_assumed_defaults
from payloq_llm.extract_pipeline import finalize_extracted_parameters
from payloq_llm.nl_param_hints import extract_starting_cash_eur, repair_starting_cash_from_nl
from payloq_llm.prompts import PARAM_SCHEMA_HINT
from payloq_schemas.models import ExtractedParameters

RUN22_DESC = (
    "Monthly revenue €180,000. Growth 0.5% per month. Starting cash €45,000. "
    "Bank covenant minimum cash €40,000. DSO 35 days. DPO 28 days. "
    "One-off CAPEX €80,000 outflow in month 3."
)

RUN22_DESC_FI = (
    "Kuukausiliikevaihto 180 000 €. Kasvu 0,5 % kuukaudessa. Alkukassa 45 000 €. "
    "Pankin kovenantti vähimmäiskassa 40 000 €. DSO 35 päivää. DPO 28 päivää. "
    "Kertaluonteinen CAPEX 80 000 € ulosmaksu kuukaudessa 3."
)

RUN22_RAW_OMITTED = {
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
    "starting_cash_eur": None,
    "covenant_min_cash_eur": 40_000,
    "special_investment_eur": None,
    "special_investment_month": None,
    "one_off_events": [
        {
            "type": "capex",
            "amount_eur": 80_000,
            "month_index": 3,
            "direction": "outflow",
        }
    ],
    "notes": "run22 ollama omit starting_cash",
    "partly_fixed_costs": None,
}


def test_prompt_documents_null_when_unstated_starting_cash() -> None:
    assert "starting_cash_eur" in PARAM_SCHEMA_HINT
    assert "null" in PARAM_SCHEMA_HINT.lower()


def test_extract_starting_cash_eur_en() -> None:
    assert extract_starting_cash_eur(RUN22_DESC) == pytest.approx(45_000)


def test_extract_starting_cash_eur_fi() -> None:
    assert extract_starting_cash_eur(RUN22_DESC_FI) == pytest.approx(45_000)


def test_extract_starting_cash_does_not_invent_when_absent() -> None:
    desc = (
        "Monthly revenue €180,000. Growth 0.5% per month. "
        "Bank covenant minimum cash €40,000. One-off CAPEX €80,000 in month 3."
    )
    assert extract_starting_cash_eur(desc) is None


def test_extract_starting_cash_ignores_covenant_and_capex() -> None:
    assert extract_starting_cash_eur(RUN22_DESC) == pytest.approx(45_000)
    no_start = RUN22_DESC.replace("Starting cash €45,000. ", "")
    assert extract_starting_cash_eur(no_start) is None


def test_repair_fills_null_from_nl_as_stated() -> None:
    raw = dict(RUN22_RAW_OMITTED)
    fixed, changes = repair_starting_cash_from_nl(RUN22_DESC, raw)
    assert fixed["starting_cash_eur"] == pytest.approx(45_000)
    assert fixed["field_sources"]["starting_cash_eur"] == "stated"
    assert any(c.get("field") == "starting_cash_eur" for c in changes)


def test_assume_fills_when_starting_cash_null() -> None:
    """Pilot fix: null starting_cash is assumed — never MissingRequired."""
    extracted = ExtractedParameters.model_validate(RUN22_RAW_OMITTED).model_dump()
    filled, changes = apply_assumed_defaults(
        extracted,
        industry="manufacturing",
        company_size="small",
        seed=22,
        description=RUN22_DESC,
        require_starting_cash=False,
    )
    assert filled["starting_cash_eur"] is not None
    assert filled["field_sources"].get("starting_cash_eur") == "assumed"
    assert any(c.get("field") == "starting_cash_eur" for c in changes)


def test_finalize_b_envelope_states_starting_cash() -> None:
    envelope = {
        "scenario_shape": "unspecified",
        "scenario_shape_quote": None,
        "stated": {
            "revenue_monthly_eur": "Monthly revenue €180,000",
            "starting_cash_eur": "Starting cash €45,000",
            "covenant_min_cash_eur": "Bank covenant minimum cash €40,000",
            "one_off_events": "One-off CAPEX €80,000 outflow in month 3",
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
                    "amount_eur": 80_000,
                    "month_index": 3,
                    "direction": "outflow",
                }
            ],
            "industry": None,
            "company_size": None,
        },
    }
    params, _changes, check = finalize_extracted_parameters(
        envelope,
        RUN22_DESC,
        industry="manufacturing",
        company_size="small",
        seed=22,
        require_starting_cash=False,
    )
    assert check.ok, check.error_text()
    assert params["starting_cash_eur"] == pytest.approx(45_000)
    assert params["field_sources"].get("starting_cash_eur") == "stated"
    assert params["special_investment_eur"] == pytest.approx(80_000)

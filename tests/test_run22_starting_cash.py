"""Run #22: map NL Starting cash / alkukassa → starting_cash_eur (stated).

Ollama omitted starting_cash_eur despite 'Starting cash €45,000' and fell to stub
after Missing required parameter retries. CAPEX €80k was already correct on stub.
"""

from __future__ import annotations

import pytest

from payloq_llm.adapters import StubLlmAdapter
from payloq_llm.assume import MissingRequiredParameterError, apply_assumed_defaults
from payloq_llm.extract_pipeline import finalize_extracted_parameters
from payloq_llm.nl_param_hints import (
    extract_starting_cash_eur,
    repair_starting_cash_from_nl,
)
from payloq_llm.prompts import PARAM_SCHEMA_HINT, parameter_repair_prompt
from payloq_schemas.models import ExtractedParameters

# Same manufacturing-style NL as Run #19 / Run #22 (EN).
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

# Ollama-shaped payload: starting_cash omitted/null despite NL (Run #22 failure).
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
            "direction": "out",
        }
    ],
    "notes": "run22 ollama omit starting_cash",
    "partly_fixed_costs": None,
}


def test_prompt_requires_starting_cash_when_nl_labels_it() -> None:
    assert "Starting cash" in PARAM_SCHEMA_HINT or "starting cash" in PARAM_SCHEMA_HINT.lower()
    assert "alkukassa" in PARAM_SCHEMA_HINT.lower()
    assert "opening cash" in PARAM_SCHEMA_HINT.lower()
    repair = parameter_repair_prompt("{}", "Missing required parameter: starting_cash_eur")
    assert "starting_cash_eur" in repair
    assert "alkukassa" in repair.lower() or "Starting cash" in repair


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
    """Covenant €40k and CAPEX €80k must not become starting cash."""
    assert extract_starting_cash_eur(RUN22_DESC) == pytest.approx(45_000)
    # Without the Starting cash clause — still no invent from covenant/CAPEX.
    no_start = RUN22_DESC.replace("Starting cash €45,000. ", "")
    assert extract_starting_cash_eur(no_start) is None


def test_repair_fills_null_from_nl_as_stated() -> None:
    raw = dict(RUN22_RAW_OMITTED)
    fixed, changes = repair_starting_cash_from_nl(RUN22_DESC, raw)
    assert fixed["starting_cash_eur"] == pytest.approx(45_000)
    assert fixed["field_sources"]["starting_cash_eur"] == "stated"
    assert any(c.get("field") == "starting_cash_eur" for c in changes)


def test_repair_does_not_invent_when_nl_has_no_figure() -> None:
    raw = dict(RUN22_RAW_OMITTED)
    desc = (
        "Monthly revenue €180,000. Growth 0.5% per month. "
        "Bank covenant minimum cash €40,000. DSO 35 days. DPO 28 days. "
        "One-off CAPEX €80,000 outflow in month 3."
    )
    fixed, changes = repair_starting_cash_from_nl(desc, raw)
    assert fixed.get("starting_cash_eur") in (None, "")
    assert changes == []


def test_assume_repairs_before_required_check() -> None:
    """Null starting_cash + NL figure → stated 45000; no MissingRequiredParameterError."""
    extracted = ExtractedParameters.model_validate(RUN22_RAW_OMITTED).model_dump()
    filled, changes = apply_assumed_defaults(
        extracted,
        industry="manufacturing",
        company_size="small",
        seed=22,
        description=RUN22_DESC,
        require_starting_cash=True,
    )
    assert filled["starting_cash_eur"] == pytest.approx(45_000)
    assert filled["field_sources"].get("starting_cash_eur") == "stated"
    assert any(
        c.get("field") == "starting_cash_eur" and "NL" in (c.get("message") or "")
        for c in changes
    )


def test_assume_errors_when_starting_cash_omitted_from_nl() -> None:
    """Truly absent from description → Missing required parameter: starting_cash_eur."""
    extracted = ExtractedParameters.model_validate(RUN22_RAW_OMITTED).model_dump()
    desc = (
        "Monthly revenue €180,000. Growth 0.5% per month. "
        "Bank covenant minimum cash €40,000. DSO 35 days. DPO 28 days. "
        "One-off CAPEX €80,000 outflow in month 3."
    )
    with pytest.raises(MissingRequiredParameterError, match="starting_cash_eur") as exc:
        apply_assumed_defaults(
            extracted,
            industry="manufacturing",
            company_size="small",
            seed=22,
            description=desc,
            require_starting_cash=True,
        )
    assert exc.value.field == "starting_cash_eur"


def test_finalize_run22_omitted_starting_cash_stated_45000() -> None:
    params, changes, grounding = finalize_extracted_parameters(
        dict(RUN22_RAW_OMITTED),
        RUN22_DESC,
        industry="manufacturing",
        company_size="small",
        seed=22,
        require_starting_cash=True,
    )
    assert grounding.ok, grounding.error_text()
    assert params["starting_cash_eur"] == pytest.approx(45_000)
    assert params["field_sources"].get("starting_cash_eur") == "stated"
    assert params["special_investment_eur"] == pytest.approx(80_000)
    assert params["field_sources"].get("special_investment_eur") == "stated"
    assert any(c.get("field") == "starting_cash_eur" for c in changes)


def test_finalize_fails_when_starting_cash_omitted_from_nl() -> None:
    desc = (
        "Monthly revenue €180,000. Growth 0.5% per month. "
        "Bank covenant minimum cash €40,000. DSO 35 days. DPO 28 days. "
        "One-off CAPEX €80,000 outflow in month 3."
    )
    with pytest.raises(MissingRequiredParameterError, match="starting_cash_eur"):
        finalize_extracted_parameters(
            dict(RUN22_RAW_OMITTED),
            desc,
            industry="manufacturing",
            company_size="small",
            seed=22,
            require_starting_cash=True,
        )


def test_stub_run22_starting_cash_45000_and_capex_80000() -> None:
    stub = StubLlmAdapter()
    out = stub.extract_parameters(
        RUN22_DESC,
        RUN22_DESC,
        {
            "industry": "manufacturing",
            "company_size": "small",
            "scenario_id": "custom",
            "language": "en",
        },
    )
    assert out["starting_cash_eur"] == pytest.approx(45_000)
    assert out["field_sources"].get("starting_cash_eur") == "stated"
    assert out["special_investment_eur"] == pytest.approx(80_000)
    assert out["special_investment_month"] == 3

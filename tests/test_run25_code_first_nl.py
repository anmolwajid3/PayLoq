"""Run #25 / #22: code-first NL extract so weak Ollama does not stub-invent.

Design: deterministic NL parse ∪ LLM JSON; code-stated wins; on total Ollama
JSON failure recover via hybrid/code-nl (not silent stub inventing €0/€180k CAPEX).
"""

from __future__ import annotations

import json

import pytest

from payloq_llm.adapters import FallbackAdapter, StubLlmAdapter, input_from_text
from payloq_llm.extract_pipeline import finalize_extracted_parameters
from payloq_llm.nl_stated import (
    build_hybrid_params_from_nl,
    extract_covenant_min_cash_eur,
    extract_dpo_days,
    extract_dso_days,
    extract_stated_params_from_nl,
    extract_stated_revenue_eur,
    merge_llm_with_code_stated,
)
from payloq_llm.assume import MissingRequiredParameterError

# Same manufacturing-style NL as Run #19 / #22 / #25.
RUN25_DESC = (
    "Monthly revenue €180,000. Growth 0.5% per month. Starting cash €45,000. "
    "Bank covenant minimum cash €40,000. DSO 35 days. DPO 28 days. "
    "One-off CAPEX €80,000 outflow in month 3."
)

RUN25_DESC_FI = (
    "Kuukausiliikevaihto 180 000 €. Kasvu 0,5 % kuukaudessa. Alkukassa 45 000 €. "
    "Pankin kovenantti vähimmäiskassa 40 000 €. DSO 35 päivää. DPO 28 päivää. "
    "Kertaluonteinen CAPEX 80 000 € ulosmaksu kuukaudessa 3."
)

# Weak llama3.2:1b-shaped: invents revenue scale + omits starting cash + wrong CAPEX.
RUN25_WEAK_LLM = {
    "monthly_revenue_start_eur": 180_000,
    "monthly_revenue_growth": None,
    "cost_shares_of_revenue": {
        "materials": None,
        "services": None,
        "personnel": None,
        "other": None,
    },
    "days_sales_outstanding": None,
    "days_payables_outstanding": None,
    "target_cash_at_end_eur": 40_000,
    "starting_cash_eur": None,
    "covenant_min_cash_eur": None,
    "special_investment_eur": 180_000,  # wrong: stole revenue as CAPEX
    "special_investment_month": 1,
    "one_off_events": [
        {"type": "capex", "amount_eur": 180_000, "month_index": 1, "direction": "outflow"}
    ],
    "notes": "weak ollama invent",
    "partly_fixed_costs": None,
}


def test_extract_stated_params_run25_en() -> None:
    stated = extract_stated_params_from_nl(RUN25_DESC)
    assert stated["starting_cash_eur"] == pytest.approx(45_000)
    assert stated["monthly_revenue_start_eur"] == pytest.approx(180_000)
    assert stated["monthly_revenue_growth"] == pytest.approx(0.005)
    assert stated["covenant_min_cash_eur"] == pytest.approx(40_000)
    assert stated["target_cash_at_end_eur"] == pytest.approx(40_000)
    assert stated["days_sales_outstanding"] == pytest.approx(35)
    assert stated["days_payables_outstanding"] == pytest.approx(28)
    assert stated["special_investment_eur"] == pytest.approx(80_000)
    assert stated["special_investment_month"] == 3
    assert stated["one_off_events"][0]["amount_eur"] == pytest.approx(80_000)
    assert stated["one_off_events"][0]["month_index"] == 3
    assert stated["one_off_events"][0]["direction"] == "outflow"
    assert stated["field_sources"]["starting_cash_eur"] == "stated"
    assert stated["field_sources"]["special_investment_eur"] == "stated"


def test_extract_stated_params_run25_fi() -> None:
    stated = extract_stated_params_from_nl(RUN25_DESC_FI)
    assert stated["starting_cash_eur"] == pytest.approx(45_000)
    assert stated["monthly_revenue_start_eur"] == pytest.approx(180_000)
    assert stated["special_investment_eur"] == pytest.approx(80_000)
    assert stated["special_investment_month"] == 3
    assert stated["days_sales_outstanding"] == pytest.approx(35)
    assert stated["days_payables_outstanding"] == pytest.approx(28)


def test_helpers_dso_dpo_covenant_revenue() -> None:
    assert extract_stated_revenue_eur(RUN25_DESC) == pytest.approx(180_000)
    assert extract_covenant_min_cash_eur(RUN25_DESC) == pytest.approx(40_000)
    assert extract_dso_days(RUN25_DESC) == pytest.approx(35)
    assert extract_dpo_days(RUN25_DESC) == pytest.approx(28)


def test_merge_locks_code_stated_over_weak_llm() -> None:
    """LLM invents €180k CAPEX / null starting cash → code locks €80k / €45k."""
    merged, changes = merge_llm_with_code_stated(
        RUN25_WEAK_LLM, extract_stated_params_from_nl(RUN25_DESC)
    )
    assert merged["starting_cash_eur"] == pytest.approx(45_000)
    assert merged["special_investment_eur"] == pytest.approx(80_000)
    assert merged["special_investment_month"] == 3
    assert merged["one_off_events"][0]["amount_eur"] == pytest.approx(80_000)
    assert merged["field_sources"]["starting_cash_eur"] == "stated"
    assert merged["field_sources"]["special_investment_eur"] == "stated"
    assert any("locked" in (c.get("message") or "") or "filled" in (c.get("message") or "") for c in changes)


def test_finalize_weak_llm_payload_stated_not_invented() -> None:
    params, changes, grounding = finalize_extracted_parameters(
        dict(RUN25_WEAK_LLM),
        RUN25_DESC,
        industry="manufacturing",
        company_size="small",
        seed=25,
        require_starting_cash=True,
    )
    assert grounding.ok, grounding.error_text()
    assert params["starting_cash_eur"] == pytest.approx(45_000)
    assert params["field_sources"].get("starting_cash_eur") == "stated"
    assert params["special_investment_eur"] == pytest.approx(80_000)
    assert params["special_investment_month"] == 3
    assert params["special_investment_eur"] != pytest.approx(180_000)
    assert params["special_investment_eur"] != pytest.approx(0)
    assert params["monthly_revenue_growth"] == pytest.approx(0.005)
    assert params["days_sales_outstanding"] == pytest.approx(35)
    assert params["days_payables_outstanding"] == pytest.approx(28)
    assert any("nl_stated" in (c.get("source") or "") for c in changes)


def test_hybrid_from_nl_without_llm_json() -> None:
    """Ollama JSON failure path: still generate from code-stated + assumed."""
    params, changes = build_hybrid_params_from_nl(
        RUN25_DESC,
        industry="manufacturing",
        company_size="small",
        seed=25,
        require_starting_cash=True,
    )
    assert params["starting_cash_eur"] == pytest.approx(45_000)
    assert params["special_investment_eur"] == pytest.approx(80_000)
    assert params["special_investment_month"] == 3
    assert params["monthly_revenue_start_eur"] == pytest.approx(180_000)
    assert "hybrid/code-nl" in (params.get("notes") or "")
    assert params.get("_extraction_mode") == "hybrid_code_nl"
    shares = params["cost_shares_of_revenue"]
    assert all(isinstance(shares[k], float) for k in ("materials", "services", "personnel", "other"))
    assert params["field_sources"].get("cost_shares_of_revenue") == "assumed"
    assert params["field_sources"].get("starting_cash_eur") == "stated"
    assert changes


def test_hybrid_errors_when_starting_cash_absent_from_nl() -> None:
    desc = (
        "Monthly revenue €180,000. Growth 0.5% per month. "
        "Bank covenant minimum cash €40,000. DSO 35 days. DPO 28 days. "
        "One-off CAPEX €80,000 outflow in month 3."
    )
    with pytest.raises(MissingRequiredParameterError, match="starting_cash_eur"):
        build_hybrid_params_from_nl(
            desc,
            industry="manufacturing",
            company_size="small",
            seed=25,
            require_starting_cash=True,
        )


def test_fallback_recovers_via_code_nl_not_stub_invent() -> None:
    """Total Ollama failure → hybrid/code-nl; CAPEX €80k not €0/€180k; sticky label."""

    class Boom(StubLlmAdapter):
        name = "ollama"

        def extract_parameters(self, description_fi, description_en, options):  # type: ignore[no-untyped-def]
            raise RuntimeError("invalid parameters JSON after retries")

    fb = FallbackAdapter(Boom(), StubLlmAdapter())
    out = fb.extract_parameters(
        RUN25_DESC,
        RUN25_DESC,
        {
            "industry": "manufacturing",
            "company_size": "small",
            "scenario_id": "custom",
            "language": "en",
            "seed": 25,
        },
    )
    assert fb.param_extraction_used_fallback is True
    assert fb.param_extraction_mode == "hybrid_code_nl"
    assert "hybrid/code-nl" in (fb.param_extraction_fallback_reason or "")
    assert out["starting_cash_eur"] == pytest.approx(45_000)
    assert out["field_sources"].get("starting_cash_eur") == "stated"
    assert out["special_investment_eur"] == pytest.approx(80_000)
    assert out["special_investment_month"] == 3
    assert out["special_investment_eur"] != pytest.approx(0)
    assert out["special_investment_eur"] != pytest.approx(180_000)
    # Sticky: later invoice-text success must not clear param fallback mode.
    fb.generate_invoice_texts(
        description_fi=RUN25_DESC,
        description_en=RUN25_DESC,
        industry="manufacturing",
        language="en",
    )
    assert fb.param_extraction_used_fallback is True
    assert fb.param_extraction_mode == "hybrid_code_nl"


def test_input_from_text_labels_hybrid_honestly() -> None:
    class Boom(StubLlmAdapter):
        name = "ollama"

        def extract_parameters(self, *a, **k):  # type: ignore[no-untyped-def]
            raise RuntimeError("ollama json fail")

    fb = FallbackAdapter(Boom(), StubLlmAdapter())
    inp = input_from_text(
        text=RUN25_DESC,
        adapter=fb,
        language="en",
        options={
            "industry": "manufacturing",
            "company_size": "small",
            "months": 12,
            "language": "en",
            "seed": 25,
        },
        with_invoice_texts=False,
    )
    assert "hybrid/code-nl" in (inp.meta.note or "")
    params = inp.parameters_from_language_model
    assert params.starting_cash_eur == pytest.approx(45_000)
    assert params.special_investment_eur == pytest.approx(80_000)


def test_code_locks_revenue_scale_against_llm_undercount() -> None:
    """Prevent €420k vs €4.2M class bug: code-stated revenue wins."""
    desc = (
        "Monthly revenue €4.2M. Growth 0.3% per month. Starting cash €1,300,000. "
        "Bank covenant minimum cash €800,000. One-off CAPEX €2.8M outflow in month 4."
    )
    llm = {
        "monthly_revenue_start_eur": 420_000,
        "monthly_revenue_growth": 0.003,
        "starting_cash_eur": 1_300_000,
        "target_cash_at_end_eur": 800_000,
        "covenant_min_cash_eur": 800_000,
        "special_investment_eur": 280_000,
        "special_investment_month": 4,
        "days_sales_outstanding": 40,
        "days_payables_outstanding": 35,
        "cost_shares_of_revenue": None,
        "one_off_events": None,
        "partly_fixed_costs": None,
    }
    params, _changes, grounding = finalize_extracted_parameters(
        llm,
        desc,
        industry="manufacturing",
        company_size="large",
        seed=17,
        require_starting_cash=True,
    )
    assert grounding.ok, grounding.error_text()
    assert params["monthly_revenue_start_eur"] == pytest.approx(4_200_000)
    assert params["special_investment_eur"] == pytest.approx(2_800_000)
    assert params["starting_cash_eur"] == pytest.approx(1_300_000)


def test_weak_llm_raw_string_still_finalizes_via_code() -> None:
    """Simulate parseable-but-weak JSON then finalize (Ollama path when JSON parses)."""
    raw = json.dumps(RUN25_WEAK_LLM)
    data = json.loads(raw)
    params, _c, grounding = finalize_extracted_parameters(
        data,
        RUN25_DESC,
        industry="manufacturing",
        company_size="small",
        seed=25,
    )
    assert grounding.ok
    assert params["starting_cash_eur"] == pytest.approx(45_000)
    assert params["special_investment_eur"] == pytest.approx(80_000)

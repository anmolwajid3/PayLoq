"""Run #10 regressions: bakery NL, Ollama incomplete JSON coerce, stub one-off €42k."""

from __future__ import annotations

from pathlib import Path

from payloq_generator.pipeline import run_generation
from payloq_llm.adapters import FallbackAdapter, StubLlmAdapter
from payloq_llm.nl_cash_intent import looks_cash_critical, suggested_target_cash_eur
from payloq_llm.nl_param_hints import (
    extract_special_investment,
    looks_bakery,
    suggest_revenue_start_eur,
)
from payloq_llm.params_coerce import coerce_parameters_dict, normalize_monthly_revenue_factors
from payloq_llm.parse import validate_model
from payloq_schemas.models import ParametersFromLanguageModel
from payloq_validate.checks import _behaviour_sid

from helpers_stub_input import generator_input_via_stub_extract

BAKERY_NL = (
    "Small Helsinki bakery. Bank covenant €10k. Winter cash ~€8k. "
    "Oven repair €42,000 in month 3. Sales soft in winter months."
)

BAKERY_FI_NL = (
    "Pieni helsinkiläinen leipomo. Pankin kovenantti 10 000 €. "
    "Talvikassa noin 8 000 €. Uunikorjaus 42 000 € kuukaudessa 3. "
    "Myynti heikko talvikuukausina."
)

# Weak llama3.2:1b-style payload: missing start/growth; euro-level "factors"
OLLAMA_INVALID_BAKERY = {
    "cost_shares_of_revenue": {
        "materials": 0.40,
        "services": 0.05,
        "personnel": 0.35,
        "other": 0.14,
    },
    "days_sales_outstanding": 35,
    "days_payables_outstanding": 28,
    "target_cash_at_end_eur": 8000,
    "special_investment_eur": 42000,
    "special_investment_month": 3,
    "monthly_revenue_factors": [
        12000,
        10000,
        11000,
        13000,
        14000,
        15000,
        15000,
        14000,
        13000,
        11000,
        10000,
        12000,
    ],
    "notes": "ollama incomplete bakery guess",
}


def test_bakery_nl_cash_and_investment_hints() -> None:
    assert looks_bakery(BAKERY_NL)
    assert looks_cash_critical(BAKERY_NL)
    sug = suggested_target_cash_eur(BAKERY_NL)
    assert sug is not None
    assert 7_000 <= sug <= 12_000
    inv = extract_special_investment(BAKERY_NL)
    assert inv is not None
    assert abs(inv[0] - 42_000) < 1.0
    assert inv[1] == 3
    rev = suggest_revenue_start_eur(
        BAKERY_NL, industry="bakery", company_size="small"
    )
    assert rev is not None
    assert 20_000 <= rev < 80_000


def test_finnish_bakery_investment_month3() -> None:
    inv = extract_special_investment(BAKERY_FI_NL)
    assert inv is not None
    assert abs(inv[0] - 42_000) < 1.0
    assert inv[1] == 3
    sug = suggested_target_cash_eur(BAKERY_FI_NL)
    assert sug is not None
    assert 7_000 <= sug <= 12_000


def test_normalize_euro_level_factors_to_multipliers() -> None:
    levels = [12000, 10000, 11000, 13000, 14000, 15000, 15000, 14000, 13000, 11000, 10000, 12000]
    factors, changes = normalize_monthly_revenue_factors(levels, start_eur=12_000)
    assert factors is not None
    assert len(factors) == 12
    assert all(0.05 <= f <= 2.0 for f in factors)
    assert any("euro levels" in str(c.get("message")) for c in changes)
    # Relative shape preserved: summer-ish > deep winter-ish
    assert factors[5] > factors[1]


def test_coerce_ollama_incomplete_bakery_json() -> None:
    """Ollama missing start_eur/growth + euro factors must become valid params."""
    data, changes = coerce_parameters_dict(
        dict(OLLAMA_INVALID_BAKERY),
        BAKERY_NL,
        options={"industry": "bakery", "company_size": "small"},
    )
    assert data.get("monthly_revenue_start_eur") not in (None, "")
    assert data.get("monthly_revenue_growth") not in (None, "")
    assert float(data["monthly_revenue_start_eur"]) < 100_000
    factors = data.get("monthly_revenue_factors")
    assert factors is not None
    assert len(factors) == 12
    assert all(0.05 <= float(f) <= 2.0 for f in factors)
    assert abs(float(data["special_investment_eur"]) - 42_000) < 1.0
    assert int(data["special_investment_month"]) == 3
    assert float(data["target_cash_at_end_eur"]) <= 12_000
    assert any(
        c.get("field") in {"monthly_revenue_start_eur", "monthly_revenue_growth", "monthly_revenue_factors"}
        or "euro levels" in str(c.get("message"))
        for c in changes
    )
    # Must validate as ParametersFromLanguageModel (no stub fallback needed)
    params = validate_model(ParametersFromLanguageModel, data)
    assert params.monthly_revenue_factors is not None
    assert len(params.monthly_revenue_factors) == 12


def test_stub_bakery_not_200k_or_80k_invest() -> None:
    params = StubLlmAdapter().extract_parameters(
        BAKERY_NL,
        BAKERY_NL,
        {"industry": "bakery", "company_size": "small"},
    )
    assert params["monthly_revenue_start_eur"] < 100_000
    assert abs(params["special_investment_eur"] - 42_000) < 1.0
    assert params["special_investment_month"] == 3
    assert params["target_cash_at_end_eur"] <= 12_000
    assert params["monthly_revenue_growth"] <= 0.001
    assert "stub:" in params["notes"]


def test_bakery_pack_passes_with_month3_oven(tmp_path: Path) -> None:
    inp = generator_input_via_stub_extract(
        text=BAKERY_NL,
        language="en",
        options={
            "industry": "bakery",
            "company_size": "small",
            "months": 12,
            "language": "en",
            "currency": "EUR",
            "as_of": "2026-10-31",
        },
    )
    params = inp.parameters_from_language_model
    assert params.monthly_revenue_start_eur < 100_000
    assert abs(params.special_investment_eur - 42_000) < 1.0
    assert params.special_investment_month == 3
    assert params.target_cash_at_end_eur <= 12_000

    outcome = run_generation(inp, tmp_path / "bakery10", seed=42, llm_name="stub")
    assert outcome.ok, (outcome.error_message, outcome.validation.issues)
    assert outcome.pack is not None
    assert _behaviour_sid(outcome.pack) == "cash_critical"
    months = outcome.pack.monthly_reports.months
    # Month-3 oven investment visible as FA step (index 2)
    fa_step = (
        months[2].balance_sheet.assets.fixed_assets
        - months[1].balance_sheet.assets.fixed_assets
    )
    assert fa_step > 30_000
    soft_ok = any(
        i.code == "behaviour_cash_critical_pnl" and i.severity == "warning"
        for i in outcome.validation.issues
    ) or not any(
        i.code == "behaviour_cash_critical_pnl" and i.severity == "error"
        for i in outcome.validation.issues
    )
    assert soft_ok


def test_fallback_coerces_before_stub_when_repairable() -> None:
    """Simulated Ollama returns incomplete JSON; coerce path avoids hard fail shape."""
    class FakeOllama(StubLlmAdapter):
        name = "ollama"

        def extract_parameters(self, description_fi, description_en, options):  # type: ignore[no-untyped-def]
            data, _ = coerce_parameters_dict(
                dict(OLLAMA_INVALID_BAKERY),
                f"{description_fi} {description_en}",
                options=options,
            )
            return validate_model(ParametersFromLanguageModel, data).model_dump()

    fb = FallbackAdapter(FakeOllama(), StubLlmAdapter())
    params = fb.extract_parameters(
        BAKERY_NL, BAKERY_NL, {"industry": "bakery", "company_size": "small"}
    )
    assert not fb.param_extraction_used_fallback
    assert abs(params["special_investment_eur"] - 42_000) < 1.0
    assert params["special_investment_month"] == 3
    assert params["monthly_revenue_start_eur"] < 100_000
    assert len(params["monthly_revenue_factors"]) == 12

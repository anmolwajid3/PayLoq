"""Run #12 regressions: mid-market steel fabricator NL — millions-scale params stick."""

from __future__ import annotations

from pathlib import Path

from payloq_generator.params_clamp import clamp_parameters
from payloq_generator.pipeline import run_generation
from payloq_llm.adapters import FallbackAdapter, StubLlmAdapter
from payloq_llm.nl_cash_intent import (
    extract_euro_amounts,
    looks_cash_critical,
    suggested_target_cash_eur,
)
from payloq_llm.nl_param_hints import (
    extract_growth_rate,
    extract_special_investment,
    looks_steel_or_manufacturing,
    suggest_revenue_start_eur,
)
from payloq_llm.params_coerce import coerce_parameters_dict
from payloq_llm.parse import validate_model
from payloq_schemas.models import ParametersFromLanguageModel

from helpers_stub_input import generator_input_via_stub_extract

STEEL_NL = (
    "Large Finnish steel fabricator, about 420 employees. "
    "Monthly revenue ~€4.2M, growth ~0.3%/month. "
    "Winter cash trough ~€1.2M; bank covenant €1.5M. "
    "Cash critical / tight through the winter. "
    "One-off CAPEX / production line investment €2.8M in month 4."
)

STEEL_FI_NL = (
    "Suuri suomalainen teräsvalmistaja, noin 420 työntekijää. "
    "Kuukausiliikevaihto noin 4,2 miljoonaa euroa, kasvu 0,3 % kuukaudessa. "
    "Talvipohja / kassapohja noin 1,2 miljoonaa euroa; pankin kovenantti 1,5 miljoonaa euroa. "
    "Kassa kriittinen / tiukalla talvella. "
    "Kertaluonteinen investointi / tuotantolinja 2,8 miljoonaa euroa kuukaudessa 4."
)

# Weak llama3.2:1b-style payload: missing start/growth; short euro-ish factors list
OLLAMA_INVALID_STEEL = {
    "cost_shares_of_revenue": {
        "materials": 0.42,
        "services": 0.08,
        "personnel": 0.32,
        "other": 0.12,
    },
    "days_sales_outstanding": 45,
    "days_payables_outstanding": 35,
    "target_cash_at_end_eur": 500_000,
    "special_investment_eur": 80_000,
    "special_investment_month": 2,
    "monthly_revenue_factors": [
        3_500_000,
        3_200_000,
        3_400_000,
        3_800_000,
        4_000_000,
        4_200_000,
        4_100_000,
    ],
    "notes": "ollama incomplete steel guess",
}


def test_parse_millions_and_steel_hints() -> None:
    amts = [a for a, _ in extract_euro_amounts(STEEL_NL)]
    assert any(abs(a - 4_200_000) < 1.0 for a in amts)
    assert any(abs(a - 2_800_000) < 1.0 for a in amts)
    assert any(abs(a - 1_200_000) < 1.0 for a in amts)
    assert any(abs(a - 1_500_000) < 1.0 for a in amts)

    assert looks_steel_or_manufacturing(STEEL_NL, industry="steel")
    assert looks_cash_critical(STEEL_NL)

    rev = suggest_revenue_start_eur(
        STEEL_NL, industry="steel", company_size="420"
    )
    assert rev is not None
    assert abs(rev - 4_200_000) / 4_200_000 < 0.08

    growth = extract_growth_rate(STEEL_NL)
    assert growth is not None
    assert abs(growth - 0.003) < 1e-4

    cash = suggested_target_cash_eur(STEEL_NL)
    assert cash is not None
    assert 1_000_000 <= cash <= 1_600_000

    inv = extract_special_investment(STEEL_NL)
    assert inv is not None
    assert abs(inv[0] - 2_800_000) / 2_800_000 < 0.05
    assert inv[1] == 4


def test_finnish_steel_millions() -> None:
    rev = suggest_revenue_start_eur(
        STEEL_FI_NL, industry="teräs", company_size="large"
    )
    assert rev is not None
    assert abs(rev - 4_200_000) / 4_200_000 < 0.08
    growth = extract_growth_rate(STEEL_FI_NL)
    assert growth is not None
    assert abs(growth - 0.003) < 1e-4
    cash = suggested_target_cash_eur(STEEL_FI_NL)
    assert cash is not None
    assert 1_000_000 <= cash <= 1_600_000
    inv = extract_special_investment(STEEL_FI_NL)
    assert inv is not None
    assert abs(inv[0] - 2_800_000) / 2_800_000 < 0.05
    assert inv[1] == 4


def test_param_ranges_keep_millions() -> None:
    params = ParametersFromLanguageModel(
        monthly_revenue_start_eur=4_200_000,
        monthly_revenue_growth=0.003,
        cost_shares_of_revenue={
            "materials": 0.42,
            "services": 0.08,
            "personnel": 0.32,
            "other": 0.12,
        },
        days_sales_outstanding=45,
        days_payables_outstanding=35,
        target_cash_at_end_eur=1_200_000,
        special_investment_eur=2_800_000,
        special_investment_month=4,
    )
    clamped, changes = clamp_parameters(params)
    assert abs(clamped.monthly_revenue_start_eur - 4_200_000) < 1.0
    assert abs(clamped.target_cash_at_end_eur - 1_200_000) < 1.0
    assert abs(clamped.special_investment_eur - 2_800_000) < 1.0
    assert not any(
        c.get("field")
        in {
            "monthly_revenue_start_eur",
            "target_cash_at_end_eur",
            "special_investment_eur",
        }
        for c in changes
    )


def test_coerce_ollama_incomplete_steel_json() -> None:
    """Ollama missing start/growth + short factors must become valid mid-market params."""
    data, changes = coerce_parameters_dict(
        dict(OLLAMA_INVALID_STEEL),
        STEEL_NL,
        options={"industry": "steel", "company_size": "420"},
    )
    assert data.get("monthly_revenue_start_eur") not in (None, "")
    assert data.get("monthly_revenue_growth") not in (None, "")
    assert abs(float(data["monthly_revenue_start_eur"]) - 4_200_000) / 4_200_000 < 0.08
    assert abs(float(data["monthly_revenue_growth"]) - 0.003) < 1e-4
    factors = data.get("monthly_revenue_factors")
    assert factors is not None
    assert len(factors) == 12
    assert all(0.05 <= float(f) <= 2.0 for f in factors)
    assert abs(float(data["special_investment_eur"]) - 2_800_000) / 2_800_000 < 0.05
    assert int(data["special_investment_month"]) == 4
    assert 1_000_000 <= float(data["target_cash_at_end_eur"]) <= 1_600_000
    validated = validate_model(ParametersFromLanguageModel, data)
    assert validated.monthly_revenue_start_eur > 1_000_000
    assert any(
        c.get("field")
        in {
            "monthly_revenue_start_eur",
            "monthly_revenue_growth",
            "special_investment_eur",
            "target_cash_at_end_eur",
            "monthly_revenue_factors",
        }
        or "euro levels" in str(c.get("message"))
        for c in changes
    )


def test_stub_steel_large_pass_level_params() -> None:
    adapter = StubLlmAdapter()
    params = adapter.extract_parameters(
        STEEL_FI_NL,
        STEEL_NL,
        {
            "industry": "steel",
            "company_size": "420",
            "months": 12,
            "language": "fi",
        },
    )
    assert abs(float(params["monthly_revenue_start_eur"]) - 4_200_000) / 4_200_000 < 0.08
    assert abs(float(params["monthly_revenue_growth"]) - 0.003) < 1e-4
    assert 1_000_000 <= float(params["target_cash_at_end_eur"]) <= 1_600_000
    assert abs(float(params["special_investment_eur"]) - 2_800_000) / 2_800_000 < 0.05
    assert int(params["special_investment_month"]) == 4
    # Must not collapse to SME invents
    assert float(params["monthly_revenue_start_eur"]) > 1_000_000
    assert float(params["special_investment_eur"]) > 1_000_000


def test_pipeline_steel_from_text_stub(tmp_path: Path) -> None:
    inp = generator_input_via_stub_extract(
        text=STEEL_NL,
        language="en",
        options={
            "industry": "steel",
            "company_size": "420",
            "months": 12,
            "language": "en",
            "currency": "EUR",
            "as_of": "2026-10-31",
        },
    )
    params = inp.parameters_from_language_model
    assert abs(params.monthly_revenue_start_eur - 4_200_000) / 4_200_000 < 0.08
    assert abs(params.monthly_revenue_growth - 0.003) < 1e-4
    assert 1_000_000 <= params.target_cash_at_end_eur <= 1_600_000
    assert abs(params.special_investment_eur - 2_800_000) / 2_800_000 < 0.05
    assert int(params.special_investment_month) == 4

    outcome = run_generation(inp, tmp_path / "steel12", seed=12, llm_name="stub")
    assert outcome.ok or not any(
        i.severity == "error" for i in outcome.validation.issues
    ), (outcome.error_message, outcome.validation.issues)
    assert outcome.pack is not None
    months = outcome.pack.monthly_reports.months
    # Month-4 CAPEX visible as FA step (index 3)
    fa_step = (
        months[3].balance_sheet.assets.fixed_assets
        - months[2].balance_sheet.assets.fixed_assets
    )
    assert fa_step > 1_000_000


def test_fallback_coerce_keeps_steel_scale() -> None:
    """Simulated Ollama returns incomplete JSON; coerce keeps mid-market scale (no stub invent)."""

    class FakeOllama(StubLlmAdapter):
        name = "ollama"

        def extract_parameters(self, description_fi, description_en, options):  # type: ignore[no-untyped-def]
            data, _ = coerce_parameters_dict(
                dict(OLLAMA_INVALID_STEEL),
                f"{description_fi} {description_en}",
                options=options,
            )
            return validate_model(ParametersFromLanguageModel, data).model_dump()

    fb = FallbackAdapter(FakeOllama(), StubLlmAdapter())
    params = fb.extract_parameters(
        STEEL_NL, STEEL_NL, {"industry": "steel", "company_size": "420"}
    )
    assert not fb.param_extraction_used_fallback
    assert abs(float(params["monthly_revenue_start_eur"]) - 4_200_000) / 4_200_000 < 0.08
    assert abs(float(params["monthly_revenue_growth"]) - 0.003) < 1e-4
    assert abs(float(params["special_investment_eur"]) - 2_800_000) / 2_800_000 < 0.05
    assert int(params["special_investment_month"]) == 4
    assert 1_000_000 <= float(params["target_cash_at_end_eur"]) <= 1_600_000
    assert len(params["monthly_revenue_factors"]) == 12

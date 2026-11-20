"""Run #9 regressions: stub vs ollama labeling, covenant target_cash, VR-20/22."""

from __future__ import annotations

from pathlib import Path

from payloq_generator.pipeline import run_generation
from payloq_llm.adapters import FallbackAdapter, StubLlmAdapter
from payloq_llm.nl_cash_intent import (
    looks_cash_critical,
    repair_params_from_nl,
    suggested_target_cash_eur,
)
from payloq_llm.nl_quality import assess_nl_params
from payloq_schemas.models import (
    CostShares,
    GeneratorInput,
    ParametersFromLanguageModel,
    ScenarioDescription,
    ScenarioMeta,
)
from payloq_validate.checks import _behaviour_sid, validate_pack

from helpers_stub_input import generator_input_via_stub_extract

HOTEL_COVENANT_NL = (
    "12-room boutique hotel. Winter cash ~€30k. Bank covenant €25k. "
    "Roof repair €95,000 in month 2. Occupancy collapses Oct-Mar."
)

HOTEL_CRITICAL_NL = (
    "A 12-room boutique hotel near the harbour; occupancy around 65% with "
    "ADR ~€180 in summer. Bookings collapse Oct–Mar (winter off-season ~0.3×). "
    "Capex: €95,000 roof repair in month 2. Cash tight and critical within weeks "
    "after a €25k supplier bill cluster. Still aiming for a profitable year on paper."
)

HOTEL_FI_NL = (
    "12 huoneen boutique-hotelli. Talvikassa noin 30 000 €. Pankin kovenantti 25 000 €. "
    "Kattoremontti 95 000 € kuukaudessa 2. Varaukset romahtavat loka–maalis. "
    "Tavoitteena silti voitollinen vuosi paperilla."
)


def test_covenant_nl_suggests_thin_target_cash() -> None:
    assert looks_cash_critical(HOTEL_COVENANT_NL)
    sug = suggested_target_cash_eur(HOTEL_COVENANT_NL)
    assert sug is not None
    assert 20_000 <= sug <= 35_000


def test_finnish_covenant_nl_suggests_thin_target_cash() -> None:
    assert looks_cash_critical(HOTEL_FI_NL)
    sug = suggested_target_cash_eur(HOTEL_FI_NL)
    assert sug is not None
    assert 20_000 <= sug <= 35_000


def test_repair_pulls_330k_down_to_covenant() -> None:
    raw = {
        "monthly_revenue_start_eur": 180_000,
        "monthly_revenue_growth": 0.008,
        "cost_shares_of_revenue": {
            "materials": 0.37,
            "services": 0.08,
            "personnel": 0.34,
            "other": 0.15,
        },
        "days_sales_outstanding": 40,
        "days_payables_outstanding": 32,
        "target_cash_at_end_eur": 330_000,
        "special_investment_eur": 95_000,
        "notes": "weak model guess",
    }
    fixed, changes = repair_params_from_nl(HOTEL_COVENANT_NL, raw)
    assert fixed["target_cash_at_end_eur"] <= 35_000
    assert fixed["monthly_revenue_growth"] == 0.0
    assert fixed["partly_fixed_costs"] is True
    assert any(c.get("field") == "target_cash_at_end_eur" for c in changes)


def test_stub_hotel_covenant_not_good_default() -> None:
    params = StubLlmAdapter().extract_parameters(
        HOTEL_COVENANT_NL, HOTEL_COVENANT_NL, {"industry": "boutique hotel"}
    )
    assert params["target_cash_at_end_eur"] <= 40_000
    assert params["monthly_revenue_growth"] <= 0.001
    assert "stub:" in params["notes"]
    assert params["special_investment_eur"] >= 95_000


def test_hotel_covenant_pack_passes_vr20_as_cash_critical(tmp_path: Path) -> None:
    inp = generator_input_via_stub_extract(
        text=HOTEL_COVENANT_NL,
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
    outcome = run_generation(inp, tmp_path / "hotel9", seed=42, llm_name="stub")
    assert outcome.ok, (outcome.error_message, outcome.validation.issues)
    assert outcome.pack is not None
    pack = outcome.pack
    assert _behaviour_sid(pack) == "cash_critical"
    # Must not be misclassified as good → behaviour_good_profit
    good_profit = [
        i for i in outcome.validation.issues if i.code == "behaviour_good_profit"
    ]
    assert not good_profit
    cash = pack.input.parameters_from_language_model.target_cash_at_end_eur
    assert cash <= 40_000
    neg = any(
        w.projected_balance < 0 for w in pack.cash_and_invoices.projection_from_open_invoices
    ) or any(p.balance < 0 for p in pack.cash_and_invoices.balance_history)
    assert neg
    # Month-2 roof investment visible
    months = pack.monthly_reports.months
    assert (
        months[1].balance_sheet.assets.fixed_assets
        - months[0].balance_sheet.assets.fixed_assets
    ) > 50_000
    assert pack.input.options.scenario_id != "good"
    assert "hotel" in (pack.input.options.scenario_id or "").lower()


def test_behaviour_good_profit_not_for_cash_critical_nl(tmp_path: Path) -> None:
    """Even with a stale behavior_profile=good stamp, stressed NL wins."""
    params = ParametersFromLanguageModel(
        monthly_revenue_start_eur=180_000,
        monthly_revenue_growth=0.0,
        cost_shares_of_revenue=CostShares(
            materials=0.37, services=0.08, personnel=0.34, other=0.15
        ),
        days_sales_outstanding=40,
        days_payables_outstanding=32,
        target_cash_at_end_eur=25_000,
        special_investment_eur=95_000,
        special_investment_month=2,
        partly_fixed_costs=True,
    )
    inp = GeneratorInput(
        meta=ScenarioMeta(
            fictional=True,
            note="parameters via ollama adapter | behavior_profile=good",
            scenario="boutique_hotel",
        ),
        scenario_description=ScenarioDescription(
            fi=HOTEL_COVENANT_NL, en=HOTEL_COVENANT_NL
        ),
        options={
            "industry": "boutique hotel",
            "company_size": "small",
            "months": 12,
            "language": "en",
            "currency": "EUR",
            "as_of": "2026-10-31",
            "scenario_id": "boutique_hotel",
        },
        parameters_from_language_model=params,
    )
    outcome = run_generation(inp, tmp_path / "beh", seed=42)
    assert outcome.pack is not None
    assert _behaviour_sid(outcome.pack) == "cash_critical"
    assert not any(
        i.code == "behaviour_good_profit" and i.severity == "error"
        for i in outcome.validation.issues
    )


def test_nl_stub_heuristic_only_when_stub_ran() -> None:
    stub_params = {
        "monthly_revenue_start_eur": 180_000,
        "monthly_revenue_growth": 0.0,
        "cost_shares_of_revenue": {
            "materials": 0.37,
            "services": 0.08,
            "personnel": 0.34,
            "other": 0.15,
        },
        "days_sales_outstanding": 40,
        "days_payables_outstanding": 32,
        "target_cash_at_end_eur": 25_000,
        "special_investment_eur": 95_000,
        "notes": "stub: cash_critical heuristic",
    }
    w_stub = assess_nl_params(
        HOTEL_CRITICAL_NL, stub_params, language="en", params_from_stub=True
    )
    assert any(w["code"] == "nl_stub_heuristic" for w in w_stub)

    live_params = dict(stub_params)
    live_params["notes"] = "ollama extraction ok"
    w_live = assess_nl_params(
        HOTEL_CRITICAL_NL, live_params, language="en", params_from_stub=False
    )
    assert not any(w["code"] == "nl_stub_heuristic" for w in w_live)


def test_fallback_keeps_param_stub_flag_after_invoice_texts() -> None:
    class Boom(StubLlmAdapter):
        name = "ollama"

        def extract_parameters(self, description_fi, description_en, options):  # type: ignore[no-untyped-def]
            raise RuntimeError("ollama down")

    fb = FallbackAdapter(Boom(), StubLlmAdapter())
    params = fb.extract_parameters(HOTEL_COVENANT_NL, HOTEL_COVENANT_NL, {})
    assert fb.param_extraction_used_fallback
    assert params["target_cash_at_end_eur"] <= 40_000
    # Later successful primary invoice-text call must not clear param fallback
    class OkTexts(Boom):
        def extract_parameters(self, description_fi, description_en, options):  # type: ignore[no-untyped-def]
            raise RuntimeError("ollama down")

        def generate_invoice_texts(self, **kwargs):  # type: ignore[no-untyped-def]
            return StubLlmAdapter().generate_invoice_texts(**kwargs)

    # Use a primary that fails extract but succeeds texts
    class Flaky(StubLlmAdapter):
        name = "ollama"

        def extract_parameters(self, *a, **k):  # type: ignore[no-untyped-def]
            raise RuntimeError("extract failed")

    fb2 = FallbackAdapter(Flaky(), StubLlmAdapter())
    fb2.extract_parameters(HOTEL_COVENANT_NL, HOTEL_COVENANT_NL, {})
    assert fb2.param_extraction_used_fallback
    fb2.generate_invoice_texts(
        description_fi=HOTEL_COVENANT_NL,
        description_en=HOTEL_COVENANT_NL,
        industry="hotel",
        language="en",
    )
    assert fb2.param_extraction_used_fallback is True
    # used_fallback may be False after a successful non-extract call
    assert fb2.param_extraction_fallback_reason


def test_cash_critical_stub_params_pass_vr20_in_pipeline(tmp_path: Path) -> None:
    """Pilot: no keyword NL repair in pipeline — use cash-critical-scale params."""
    inp = generator_input_via_stub_extract(
        text=HOTEL_COVENANT_NL,
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
    outcome = run_generation(inp, tmp_path / "repair", seed=42, llm_name="stub")
    assert outcome.ok, outcome.error_message
    assert outcome.pack is not None
    assert outcome.pack.input.parameters_from_language_model.target_cash_at_end_eur <= 40_000
    assert _behaviour_sid(outcome.pack) == "cash_critical"
    assert not any(i.code == "behaviour_good_profit" for i in outcome.validation.issues)

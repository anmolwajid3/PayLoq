"""VR-13 / FR-A-32: invoice free-text fields must not contain digits."""

from __future__ import annotations

from pathlib import Path

from payloq_generator.engine import generate_pack
from payloq_generator.pipeline import run_generation
from payloq_llm.adapters import StubLlmAdapter, input_from_text
from payloq_llm.text_sanitize import sanitize_invoice_texts
from payloq_schemas.models import InvoiceDescriptiveTexts, ParametersFromLanguageModel
from payloq_schemas.text_rules import (
    descriptive_text_has_numbers,
    strip_numbers_from_descriptive_text,
)
from payloq_validate.checks import validate_pack

# Alpha Run #6 style: boutique hotel NL packed with digits / € amounts.
BOUTIQUE_HOTEL_NL = (
    "A 12-room boutique hotel near the harbour; occupancy around 65% with "
    "ADR ~€180. Capex of ~€30k for lobby refresh and a €95,000 HVAC quote; "
    "cash tight for 45 days after a €25k supplier bill cluster. "
    "Still aiming for a profitable year on paper."
)


class DigitsLeakingAdapter(StubLlmAdapter):
    """Simulates small Ollama models that paste NL numbers into invoice texts."""

    name = "digits_leak"

    def generate_invoice_texts(
        self,
        *,
        description_fi: str,
        description_en: str,
        industry: str,
        language: str = "fi",
    ) -> InvoiceDescriptiveTexts:
        _ = industry
        blob = description_fi or description_en
        return InvoiceDescriptiveTexts(
            sales_counterparties=[
                "Harbour Stay Oy 12",
                "Guest Co €180",
                "Lobby Events 65%",
                "Suite Partner Oy",
                "Weekend Group Oy",
                "Spa Day Oy",
                "Conference Nord Oy",
                "City Break Oy",
            ],
            purchase_counterparties=[
                "HVAC Quote Oy €95,000",
                "Lobby Capex Oy ~€30k",
                "Supplier Cluster 25k",
                "Linen Service Oy",
                "Food Market Oy",
                "Energy Utility Oy",
                "Cleaning Pro Oy",
                "Insurance Nord Oy",
            ],
            sales_descriptions=[
                blob,  # raw from_text paste
                "12-room night package",
                "ADR ~€180 weekend",
                "Conference day 45 guests",
                "Spa package",
                "Harbour view suite",
            ],
            purchase_descriptions=[
                "HVAC quote €95,000",
                "Lobby refresh ~€30k",
                "Supplier bill €25k",
                "Linen service monthly",
                "Food supplies",
                "45 days energy",
            ],
            language="en" if language == "en" else "fi",
            notes="deliberately dirty for VR-13 regression",
        )


def test_strip_numbers_removes_euro_amounts() -> None:
    samples = [
        "12-room boutique stay",
        "Capex ~€30k lobby",
        "HVAC quote €95,000",
        "bill €25k cluster",
        "ADR ~€180",
        "occupancy 65%",
        "cash tight for 45 days",
    ]
    for s in samples:
        cleaned = strip_numbers_from_descriptive_text(s)
        assert not descriptive_text_has_numbers(cleaned), (s, cleaned)


def test_sanitize_replaces_pasted_nl_and_digits() -> None:
    dirty = DigitsLeakingAdapter().generate_invoice_texts(
        description_fi=BOUTIQUE_HOTEL_NL,
        description_en=BOUTIQUE_HOTEL_NL,
        industry="boutique hotel",
        language="en",
    )
    clean = sanitize_invoice_texts(
        dirty, description_fi=BOUTIQUE_HOTEL_NL, description_en=BOUTIQUE_HOTEL_NL
    )
    for field in (
        clean.sales_counterparties
        + clean.purchase_counterparties
        + clean.sales_descriptions
        + clean.purchase_descriptions
    ):
        assert not descriptive_text_has_numbers(field), field
        assert field.lower().strip() != BOUTIQUE_HOTEL_NL.lower().strip()


def test_from_text_digit_heavy_nl_passes_vr13(tmp_path: Path) -> None:
    adapter = DigitsLeakingAdapter(
        preset=ParametersFromLanguageModel(
            monthly_revenue_start_eur=180_000.0,
            monthly_revenue_growth=0.0,
            cost_shares_of_revenue={
                "materials": 0.20,
                "services": 0.15,
                "personnel": 0.35,
                "other": 0.18,
            },
            days_sales_outstanding=40.0,
            days_payables_outstanding=28.0,
            target_cash_at_end_eur=40_000.0,
            special_investment_eur=95_000.0,
            notes="boutique hotel cash-critical style params",
            partly_fixed_costs=True,
        )
    )
    inp = input_from_text(
        text=BOUTIQUE_HOTEL_NL,
        adapter=adapter,
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
    assert inp.invoice_texts is not None
    for field in (
        inp.invoice_texts.sales_descriptions
        + inp.invoice_texts.purchase_descriptions
        + inp.invoice_texts.sales_counterparties
        + inp.invoice_texts.purchase_counterparties
    ):
        assert not descriptive_text_has_numbers(field), field

    outcome = run_generation(inp, tmp_path / "hotel", seed=42)
    assert outcome.pack is not None
    # Hard VR-13 errors must be gone even if seed retries were needed for other rules.
    vr13 = [
        i
        for i in outcome.validation.issues
        if i.severity == "error" and (i.rule_id == "VR-13" or i.code == "text_has_numbers")
    ]
    assert not vr13, vr13
    for inv in outcome.pack.cash_and_invoices.open_invoices:
        assert not descriptive_text_has_numbers(inv.counterparty), inv.counterparty
        assert not descriptive_text_has_numbers(inv.description), inv.description
        # Invoice numbers (ids) remain allowed / present.
        assert inv.id.startswith(("S-", "P-"))


def test_generate_pack_sanitizes_dirty_invoice_texts() -> None:
    from payloq_generator.engine import load_input

    root = Path(__file__).resolve().parents[1]
    inp = load_input(root / "scenarios" / "cash_critical" / "input.json")
    inp = inp.model_copy(
        update={
            "invoice_texts": InvoiceDescriptiveTexts(
                sales_counterparties=["Customer 12 Oy"],
                purchase_counterparties=["Supplier €30k Oy"],
                sales_descriptions=["Batch of 500 parts"],
                purchase_descriptions=["Steel order 45 days"],
                language="fi",
            )
        }
    )
    pack = generate_pack(inp, seed=42)
    result = validate_pack(pack)
    vr13 = [i for i in result.issues if i.rule_id == "VR-13" and i.severity == "error"]
    assert not vr13, vr13


def test_cash_critical_pnl_is_soft_warning() -> None:
    """Unprofitable cash_critical must not hard-fail VR-20 pnl (from_text soft path)."""
    from payloq_generator.engine import load_input
    from payloq_schemas.models import CostShares

    root = Path(__file__).resolve().parents[1]
    inp = load_input(root / "scenarios" / "cash_critical" / "input.json")
    # Force high cost shares → overall losses while keeping cash_critical id.
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
    inp = inp.model_copy(update={"parameters_from_language_model": params})
    pack = generate_pack(inp, seed=42)
    nets = sum(m.income_statement.net_result for m in pack.monthly_reports.months)
    assert nets <= 0, "test setup should produce overall losses"
    result = validate_pack(pack)
    pnl = [i for i in result.issues if i.code == "behaviour_cash_critical_pnl"]
    assert pnl, "expected pnl soft warning when cash_critical is unprofitable"
    assert all(i.severity == "warning" for i in pnl)
    hard_pnl = [i for i in pnl if i.severity == "error"]
    assert not hard_pnl
    # Pack may still fail other hard rules; pnl alone must not be an error.
    assert "VR-20" not in [
        i.rule_id for i in result.issues if i.severity == "error" and i.code == "behaviour_cash_critical_pnl"
    ]

"""The run seed must reach extraction-time assumed values (not a hidden 42)."""

from __future__ import annotations

from payloq_llm.adapters import default_options_from_text, input_from_text
from payloq_schemas.models import ParametersFromLanguageModel  # noqa: F401  (import check)

from harness.adapter import FixtureAdapter

TEXT = "Monthly revenue 210,000 euro. Starting cash 65,000 euro. Bank minimum cash 50,000 euro."
EXTRACTION = {
    "scenario_shape": "cash_critical",
    "scenario_shape_quote": "cash",
    "stated": {
        "revenue_monthly_eur": "Monthly revenue 210,000 euro.",
        "starting_cash_eur": "Starting cash 65,000 euro.",
        "covenant_min_cash_eur": "Bank minimum cash 50,000 euro.",
    },
    "parameters": {
        "revenue_monthly_eur": 210000,
        "starting_cash_eur": 65000,
        "covenant_min_cash_eur": 50000,
    },
}


def _target_for_seed(seed: int) -> float:
    adapter = FixtureAdapter()
    adapter.bind(EXTRACTION)
    opts = default_options_from_text(language="en", seed=seed)
    inp = input_from_text(
        text=TEXT, adapter=adapter, language="en", options=opts, with_invoice_texts=False
    )
    return float(inp.parameters_from_language_model.target_cash_at_end_eur)


def test_options_carry_the_run_seed() -> None:
    assert default_options_from_text(language="en", seed=15)["seed"] == 15


def test_assumed_target_cash_changes_with_run_seed() -> None:
    # Before the fix every seed drew the seed-42 value (16,964.88) here.
    assert _target_for_seed(15) != _target_for_seed(42)

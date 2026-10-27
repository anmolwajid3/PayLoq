"""Phase 2: NL → params (stub), descriptive texts, parse helpers; optional Ollama."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from payloq_generator.engine import generate_pack, write_pack
from payloq_llm.adapters import (
    FallbackAdapter,
    OllamaAdapter,
    StubLlmAdapter,
    get_adapter,
    input_from_text,
)
from payloq_llm.defaults import DEFAULT_OLLAMA_MODEL
from payloq_llm.parse import extract_json_object
from payloq_schemas.models import InvoiceDescriptiveTexts, ParametersFromLanguageModel
from payloq_validate.checks import validate_pack

CASH_CRITICAL_FI = (
    "Pieni konepaja, tulos on positiivinen mutta kassa on tiukalla nyt ja "
    "kriittinen kolmen viikon päästä, koska isot ostolaskut erääntyvät ennen "
    "myyntilaskujen maksuja."
)


def test_extract_json_object_from_fence() -> None:
    raw = 'Here you go:\n```json\n{"a": 1, "b": "x"}\n```\nThanks'
    assert extract_json_object(raw) == {"a": 1, "b": "x"}


def test_stub_extract_cash_critical_keywords() -> None:
    adapter = StubLlmAdapter()
    params = adapter.extract_parameters(CASH_CRITICAL_FI, "cash critical in three weeks", {})
    validated = ParametersFromLanguageModel.model_validate(params)
    assert validated.target_cash_at_end_eur <= 60_000
    assert validated.partly_fixed_costs is True


def test_stub_invoice_texts_fi() -> None:
    texts = StubLlmAdapter().generate_invoice_texts(
        description_fi=CASH_CRITICAL_FI,
        description_en="cash critical",
        industry="metal workshop",
        language="fi",
    )
    assert isinstance(texts, InvoiceDescriptiveTexts)
    assert texts.language == "fi"
    assert len(texts.sales_counterparties) >= 8
    assert all("Oy" in c or "oy" in c.lower() for c in texts.sales_counterparties[:3])


def test_from_text_stub_generates_valid_cash_critical_pack(tmp_path: Path) -> None:
    adapter = get_adapter("stub")
    inp = input_from_text(text=CASH_CRITICAL_FI, adapter=adapter, language="fi")
    assert inp.invoice_texts is not None
    pack = generate_pack(inp, seed=42)
    result = validate_pack(pack)
    errors = [i for i in result.issues if i.severity == "error"]
    assert not errors, errors

    proj = pack.cash_and_invoices.projection_from_open_invoices
    neg = [w.week for w in proj if w.projected_balance < 0]
    assert neg, "expected near-term negative cash from cash-critical NL"
    assert min(neg) <= 4

    write_pack(pack, tmp_path / "nl", write_xlsx=False)
    saved = json.loads((tmp_path / "nl" / "input.json").read_text(encoding="utf-8"))
    assert saved.get("invoice_texts")
    assert saved["parameters_from_language_model"]["target_cash_at_end_eur"] <= 60_000


def test_scenario_presets_still_work_without_llm() -> None:
    """Regression: --scenario path must not require invoice_texts on disk."""
    from payloq_generator.engine import load_input

    root = Path(__file__).resolve().parents[1]
    inp = load_input(root / "scenarios" / "good" / "input.json")
    assert inp.invoice_texts is None
    pack = generate_pack(inp, seed=42)
    assert validate_pack(pack).ok
    # Built-in FI counterparties still applied
    sales = [i for i in pack.cash_and_invoices.open_invoices if i.type == "sales"]
    assert sales[0].counterparty


def test_fallback_adapter_uses_stub_when_primary_fails() -> None:
    class Boom(StubLlmAdapter):
        name = "boom"

        def extract_parameters(self, description_fi, description_en, options):  # type: ignore[no-untyped-def]
            raise RuntimeError("ollama down")

    fb = FallbackAdapter(Boom(), StubLlmAdapter())
    params = fb.extract_parameters(CASH_CRITICAL_FI, "x", {})
    assert fb.used_fallback
    assert "ollama down" in (fb.last_fallback_reason or "")
    ParametersFromLanguageModel.model_validate(params)


def test_get_adapter_ollama_wraps_fallback() -> None:
    adapter = get_adapter("ollama", fallback_stub=True, model=DEFAULT_OLLAMA_MODEL)
    assert isinstance(adapter, FallbackAdapter)
    assert isinstance(adapter.primary, OllamaAdapter)
    assert adapter.primary.model == DEFAULT_OLLAMA_MODEL


def test_ollama_unavailable_falls_back() -> None:
    adapter = get_adapter(
        "ollama",
        fallback_stub=True,
        host="http://127.0.0.1:1",  # nothing listening
        model=DEFAULT_OLLAMA_MODEL,
    )
    assert isinstance(adapter, FallbackAdapter)
    params = adapter.extract_parameters(CASH_CRITICAL_FI, "critical", {})
    assert adapter.used_fallback
    ParametersFromLanguageModel.model_validate(params)


@pytest.mark.integration
def test_ollama_live_optional() -> None:
    """Skipped unless a local Ollama serves the default model."""
    primary = OllamaAdapter(model=DEFAULT_OLLAMA_MODEL)
    if not primary.is_available():
        pytest.skip("Ollama not reachable at default host")
    # Model may still be missing — skip on hard failure
    try:
        params = primary.extract_parameters(
            CASH_CRITICAL_FI,
            "Cash becomes critical in three weeks.",
            {
                "industry": "metal workshop",
                "company_size": "small",
                "months": 12,
                "language": "fi",
                "currency": "EUR",
            },
        )
    except RuntimeError as exc:
        pytest.skip(f"Ollama present but call failed: {exc}")
    validated = ParametersFromLanguageModel.model_validate(params)
    assert validated.monthly_revenue_start_eur > 0

"""Pilot fix H1–H8: generator must follow work-order extract / assume / fidelity rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from payloq_llm.adapters import OllamaAdapter, get_adapter, input_from_text
from payloq_llm.defaults import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_MODEL
from payloq_llm.extract_pipeline import finalize_extracted_parameters
from payloq_llm.extraction_schema import EXTRACTION_JSON_SCHEMA
from payloq_generator.pipeline import run_generation


VAGUE = "A small machine shop, cash is tight now and critical in three weeks."
FULLY_STATED = (
    "Monthly revenue 200,000 euro. Growth 0.5% per month. Starting cash 45,000 euro. "
    "Bank minimum cash 40,000 euro. DSO 35 days. DPO 28 days. "
    "One-off outflow of 80,000 euro in month 3."
)
RUN23 = (
    "Manufacturing firm. Monthly revenue 180,000 euro. Growth 0.5% per month. "
    "Starting cash 45,000 euro. Bank minimum cash 40,000 euro. DSO 35 days. DPO 28 days. "
    "One-off CAPEX 80,000 euro outflow in month 3."
)
RUN27 = (
    "Monthly revenue 180,000 euro. One-off investment 80,000 euro outflow in month 3."
)
TWO_VALUE = "Starting cash 45,000 euro. Bank minimum cash 40,000 euro."


def _ollama_ready() -> bool:
    adapter = OllamaAdapter(model=DEFAULT_OLLAMA_MODEL, host=DEFAULT_OLLAMA_HOST, timeout_s=5)
    if not adapter.is_available():
        return False
    # Model must be present
    import urllib.request

    try:
        req = urllib.request.Request(f"{DEFAULT_OLLAMA_HOST.rstrip('/')}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = {m.get("name") or m.get("model") for m in data.get("models") or []}
        return any(
            DEFAULT_OLLAMA_MODEL == n or n.startswith(DEFAULT_OLLAMA_MODEL.split(":")[0])
            for n in names
            if n
        )
    except Exception:
        return False


requires_ollama = pytest.mark.skipif(
    not _ollama_ready(),
    reason=f"Ollama + {DEFAULT_OLLAMA_MODEL} required for H live tests",
)


def _opts(**kwargs: Any) -> dict[str, Any]:
    base = {
        "industry": "metal workshop (machine shop)",
        "company_size": "small",
        "months": 12,
        "language": "en",
        "seed": 42,
    }
    base.update(kwargs)
    return base


def _stated_snapshot(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "starting_cash_eur": params.get("starting_cash_eur"),
        "covenant_min_cash_eur": params.get("covenant_min_cash_eur"),
        "monthly_revenue_start_eur": params.get("monthly_revenue_start_eur"),
        "special_investment_eur": params.get("special_investment_eur"),
        "special_investment_month": params.get("special_investment_month"),
        "field_sources": params.get("field_sources"),
        "stated_values": params.get("stated_values"),
        "scenario_shape": params.get("scenario_shape"),
    }


@requires_ollama
def test_h1_vague_ok_cash_negative_around_week3(tmp_path: Path):
    adapter = get_adapter(
        "ollama",
        fallback_stub=False,
        model=DEFAULT_OLLAMA_MODEL,
        host=DEFAULT_OLLAMA_HOST,
        timeout_s=600,
    )
    inp = input_from_text(
        text=VAGUE,
        adapter=adapter,
        language="en",
        options=_opts(),
        with_invoice_texts=False,
    )
    outcome = run_generation(
        inp,
        tmp_path / "h1",
        seed=42,
        write_xlsx=False,
                llm_name="ollama",
        raw_llm_output=adapter.last_raw_output,
    )
    params = inp.parameters_from_language_model.model_dump()
    print("H1 stated snapshot:", _stated_snapshot(params))
    assert outcome.ok, outcome.error_message or outcome.validation.as_dict()
    assert not (tmp_path / "h1" / "journal_entries.json").exists()
    # Cash negative around week 3 in history or early projection
    cash = outcome.pack.cash_and_invoices if outcome.pack else None
    assert cash is not None
    neg_hist = [p for p in cash.balance_history if p.balance < 0 and p.week <= 5]
    neg_proj = [
        w
        for w in cash.projection_from_open_invoices
        if w.projected_balance < 0 and w.week <= 5
    ]
    assert neg_hist or neg_proj or params.get("scenario_shape") == "cash_critical"


@requires_ollama
def test_h2_fully_stated_exact_fields(tmp_path: Path):
    adapter = get_adapter(
        "ollama", fallback_stub=False, model=DEFAULT_OLLAMA_MODEL, timeout_s=600
    )
    inp = input_from_text(
        text=FULLY_STATED,
        adapter=adapter,
        language="en",
        options=_opts(),
        with_invoice_texts=False,
    )
    params = inp.parameters_from_language_model.model_dump()
    print("H2 stated snapshot:", _stated_snapshot(params))
    assert params["starting_cash_eur"] == pytest.approx(45_000, rel=0, abs=1)
    assert params["covenant_min_cash_eur"] == pytest.approx(40_000, rel=0, abs=1)
    assert params["special_investment_eur"] == pytest.approx(80_000, rel=0, abs=1)
    assert int(params["special_investment_month"]) == 3
    sources = params.get("field_sources") or {}
    assert sources.get("starting_cash_eur") == "stated"
    outcome = run_generation(
        inp, tmp_path / "h2", seed=42, write_xlsx=False
    )
    assert outcome.ok, outcome.validation.as_dict()


@requires_ollama
def test_h3_run23_revenue_not_confused_with_cash(tmp_path: Path):
    adapter = get_adapter(
        "ollama", fallback_stub=False, model=DEFAULT_OLLAMA_MODEL, timeout_s=600
    )
    inp = input_from_text(
        text=RUN23, adapter=adapter, language="en", options=_opts(), with_invoice_texts=False
    )
    params = inp.parameters_from_language_model.model_dump()
    print("H3 stated snapshot:", _stated_snapshot(params))
    assert params["monthly_revenue_start_eur"] == pytest.approx(180_000, rel=0, abs=1)
    assert params["starting_cash_eur"] == pytest.approx(45_000, rel=0, abs=1)
    assert params["covenant_min_cash_eur"] == pytest.approx(40_000, rel=0, abs=1)
    outcome = run_generation(
        inp, tmp_path / "h3", seed=42, write_xlsx=False
    )
    assert outcome.ok, outcome.validation.as_dict()


@requires_ollama
def test_h4_run27_partial_stated_rest_assumed(tmp_path: Path):
    adapter = get_adapter(
        "ollama", fallback_stub=False, model=DEFAULT_OLLAMA_MODEL, timeout_s=600
    )
    # Capture raw model output before assume by re-extracting via finalize on raw
    inp = input_from_text(
        text=RUN27, adapter=adapter, language="en", options=_opts(), with_invoice_texts=False
    )
    params = inp.parameters_from_language_model.model_dump()
    print("H4 stated snapshot:", _stated_snapshot(params))
    assert params["monthly_revenue_start_eur"] == pytest.approx(180_000, rel=0, abs=1)
    assert params["special_investment_eur"] == pytest.approx(80_000, rel=0, abs=1)
    sources = params.get("field_sources") or {}
    assert sources.get("monthly_revenue_start_eur") == "stated"
    assert sources.get("special_investment_eur") == "stated"
    assert sources.get("monthly_revenue_growth") == "assumed"
    assert sources.get("starting_cash_eur") == "assumed"
    assert sources.get("covenant_min_cash_eur") == "assumed" or sources.get(
        "target_cash_at_end_eur"
    ) == "assumed"
    # No zeros for growth / starting as "stated" inventions
    raw = adapter.last_raw_output or ""
    if raw:
        data = json.loads(raw) if raw.strip().startswith("{") else None
        if data is None:
            from payloq_llm.parse import extract_json_object

            data = extract_json_object(raw)
        model_params = data.get("parameters") or data
        assert model_params.get("growth_per_month_fraction") in (None, )
        assert model_params.get("starting_cash_eur") in (None, )
        assert model_params.get("covenant_min_cash_eur") in (None, )
    outcome = run_generation(
        inp, tmp_path / "h4", seed=42, write_xlsx=False
    )
    assert outcome.ok, outcome.validation.as_dict()


def test_h5_unreachable_ollama_errors_no_files(tmp_path: Path):
    adapter = OllamaAdapter(
        model=DEFAULT_OLLAMA_MODEL,
        host="http://127.0.0.1:9",
        timeout_s=2,
        http_timeout_retries=0,
    )
    out = tmp_path / "h5"
    out.mkdir()
    with pytest.raises(Exception):
        input_from_text(
            text=VAGUE,
            adapter=adapter,
            language="en",
            options=_opts(),
            with_invoice_texts=False,
        )
    assert list(out.glob("*.json")) == []


def test_h6_invalid_json_errors():
    class BadOllama(OllamaAdapter):
        def _chat(self, *args: Any, **kwargs: Any) -> str:  # type: ignore[override]
            return "NOT JSON {{{"

    adapter = BadOllama(model=DEFAULT_OLLAMA_MODEL, host=DEFAULT_OLLAMA_HOST, timeout_s=5)
    with pytest.raises(Exception):
        adapter.extract_parameters(VAGUE, VAGUE, _opts())


@requires_ollama
def test_h7_two_value_not_swapped():
    adapter = get_adapter(
        "ollama", fallback_stub=False, model=DEFAULT_OLLAMA_MODEL, timeout_s=600
    )
    inp = input_from_text(
        text=TWO_VALUE,
        adapter=adapter,
        language="en",
        options=_opts(),
        with_invoice_texts=False,
    )
    params = inp.parameters_from_language_model.model_dump()
    print("H7 stated snapshot:", _stated_snapshot(params))
    assert params["starting_cash_eur"] == pytest.approx(45_000, rel=0, abs=1)
    assert params["covenant_min_cash_eur"] == pytest.approx(40_000, rel=0, abs=1)
    assert params["starting_cash_eur"] != params["covenant_min_cash_eur"]


@requires_ollama
def test_h8_repeatability_same_seed():
    adapter = get_adapter(
        "ollama", fallback_stub=False, model=DEFAULT_OLLAMA_MODEL, timeout_s=600
    )
    opts = _opts(seed=42)
    a = input_from_text(
        text=VAGUE, adapter=adapter, language="en", options=opts, with_invoice_texts=False
    )
    b = input_from_text(
        text=VAGUE, adapter=adapter, language="en", options=opts, with_invoice_texts=False
    )
    pa = a.parameters_from_language_model.model_dump()
    pb = b.parameters_from_language_model.model_dump()
    # Drop volatile notes
    for p in (pa, pb):
        p.pop("notes", None)
        p.pop("llm_model_name", None)
        p.pop("conversion_notes", None)
    assert pa == pb


def test_default_model_is_qwen25_7b():
    assert DEFAULT_OLLAMA_MODEL == "qwen2.5:7b"


def test_extraction_schema_has_section_b_keys():
    props = EXTRACTION_JSON_SCHEMA["properties"]
    assert "scenario_shape" in props
    assert "stated" in props
    assert "parameters" in props


def test_assume_starting_cash_never_required():
    raw = {
        "scenario_shape": "cash_critical",
        "scenario_shape_quote": "critical in three weeks",
        "stated": {},
        "parameters": {
            "revenue_monthly_eur": None,
            "revenue_annual_eur": None,
            "growth_per_month_fraction": None,
            "starting_cash_eur": None,
            "covenant_min_cash_eur": None,
            "dso_days": None,
            "dpo_days": None,
            "one_off_events": [],
            "industry": None,
            "company_size": None,
        },
    }
    params, changes, check = finalize_extracted_parameters(
        raw,
        VAGUE,
        industry="machine shop",
        company_size="small",
        seed=42,
        require_starting_cash=False,
    )
    assert check.ok
    assert params["starting_cash_eur"] is not None
    assert params["field_sources"]["starting_cash_eur"] == "assumed"
    assert any(c.get("field") == "starting_cash_eur" for c in changes)


def test_stub_adapter_rejected_for_from_text():
    from payloq_llm.adapters import StubLlmAdapter

    with pytest.raises(ValueError, match="stub"):
        input_from_text(text=VAGUE, adapter=StubLlmAdapter(), language="en")

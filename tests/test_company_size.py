"""FR-A-02 / FR-A-06: company size as employee count or small/medium/large."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from payloq_generator.pipeline import run_generation
from payloq_llm.adapters import StubLlmAdapter, default_options_from_text, input_from_text
from payloq_schemas.company_size import (
    INVALID_MSG,
    MISSING_MSG,
    parse_company_size,
    scale_defaults_for_size,
    size_band,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("small", "small"),
        ("SMALL", "small"),
        ("medium", "medium"),
        ("Medium", "medium"),
        ("large", "large"),
        ("Large", "large"),
        ("LARGE", "large"),
        ("pieni", "small"),
        ("keskikokoinen", "medium"),
        ("suuri", "large"),
        ("iso", "large"),
        ("8", "8 employees"),
        (8, "8 employees"),
        ("420", "420 employees"),
        (420, "420 employees"),
        ("12 employees", "12 employees"),
        ("12 employee", "12 employees"),
        ("12 Employees", "12 employees"),
        ("12 työntekijää", "12 employees"),
        ("  8  ", "8 employees"),
    ],
)
def test_parse_company_size_ok(raw: object, expected: str) -> None:
    assert parse_company_size(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_parse_company_size_missing(raw: object) -> None:
    with pytest.raises(ValueError, match="Company size is missing"):
        parse_company_size(raw)


@pytest.mark.parametrize("raw", ["huge", "enterprise", "sme", "0", "-3", "abc", "12.5", True])
def test_parse_company_size_invalid(raw: object) -> None:
    with pytest.raises(ValueError, match="must be a number of employees"):
        parse_company_size(raw)


@pytest.mark.parametrize(
    "canonical,expected",
    [
        ("small", "small"),
        ("medium", "medium"),
        ("large", "large"),
        ("8 employees", "small"),
        ("49 employees", "small"),
        ("50 employees", "medium"),
        ("249 employees", "medium"),
        ("250 employees", "large"),
        ("420 employees", "large"),
    ],
)
def test_size_band(canonical: str, expected: str) -> None:
    assert size_band(canonical) == expected


def test_scale_defaults_large_above_small() -> None:
    small = scale_defaults_for_size("small")
    large = scale_defaults_for_size("large")
    mid = scale_defaults_for_size("420 employees")
    assert large["band"] == "large"
    assert mid["band"] == "large"
    assert large["monthly_revenue_start_eur"] > small["monthly_revenue_start_eur"]
    assert large["cash_mult"] > small["cash_mult"]
    assert mid["monthly_revenue_start_eur"] == large["monthly_revenue_start_eur"]


def test_from_text_persists_size_label_and_seed(tmp_path: Path) -> None:
    opts = default_options_from_text(
        industry="machine shop",
        company_size=parse_company_size("small"),
        months=12,
        language="en",
    )
    inp = input_from_text(
        text="A small machine shop with tight cash.",
        adapter=StubLlmAdapter(),
        language="en",
        options=opts,
    )
    assert inp.options.company_size == "small"
    outcome = run_generation(inp, tmp_path / "label", seed=99, llm_name="stub")
    assert outcome.ok
    written = json.loads((outcome.out_dir / "input.json").read_text(encoding="utf-8"))
    assert written["options"]["company_size"] == "small"
    assert written["options"]["industry"] == "machine shop"
    assert written["options"]["months"] == 12
    run_log = json.loads((outcome.out_dir / "run_log.json").read_text(encoding="utf-8"))
    assert run_log["seed"] == outcome.seed_used
    assert run_log["options"]["company_size"] == "small"


def test_from_text_persists_employee_count(tmp_path: Path) -> None:
    size = parse_company_size("12 employees")
    opts = default_options_from_text(company_size=size, months=18, language="fi")
    inp = input_from_text(
        text="Pieni konepaja, kassa on kriittinen.",
        adapter=StubLlmAdapter(),
        language="fi",
        options=opts,
    )
    assert inp.options.company_size == "12 employees"
    outcome = run_generation(inp, tmp_path / "emps", seed=42, llm_name="stub")
    assert outcome.ok
    written = json.loads((outcome.out_dir / "input.json").read_text(encoding="utf-8"))
    assert written["options"]["company_size"] == "12 employees"
    assert written["options"]["months"] == 18


def test_stub_scales_large_company_size() -> None:
    adapter = StubLlmAdapter()
    small = adapter.extract_parameters(
        "Konepaja, kassa on kriittinen kolmen viikon päästä.",
        "Machine shop, cash critical in three weeks.",
        default_options_from_text(company_size="small"),
    )
    large = adapter.extract_parameters(
        "Terästehdas, kassa on kriittinen kolmen viikon päästä.",
        "Steel plant, cash critical in three weeks.",
        default_options_from_text(company_size="large"),
    )
    headcount = adapter.extract_parameters(
        "Terästehdas, kassa on kriittinen kolmen viikon päästä.",
        "Steel plant, cash critical in three weeks.",
        default_options_from_text(company_size="420 employees"),
    )
    assert small["monthly_revenue_start_eur"] == 200_000.0
    assert large["monthly_revenue_start_eur"] == 1_200_000.0
    assert headcount["monthly_revenue_start_eur"] == 1_200_000.0
    assert large["target_cash_at_end_eur"] > small["target_cash_at_end_eur"]
    assert "band=large" in (large.get("notes") or "")


def test_error_message_constants() -> None:
    assert "small, medium, large" in MISSING_MSG
    assert "small, medium, large" in INVALID_MSG

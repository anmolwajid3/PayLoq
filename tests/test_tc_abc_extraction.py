"""TC-A/B/C extraction helpers: value grounding, clean output, one-off enforce."""

from __future__ import annotations

from payloq_llm.extract_pipeline import finalize_extracted_parameters
from payloq_llm.stated_checks import (
    check_stated_values,
    clean_extraction_output,
    enforce_required_one_offs,
    extract_required_one_offs,
    scan_description_numbers,
)


def test_scan_description_numbers_formats() -> None:
    desc = (
        "Monthly revenue 210,000 euro. Starting cash 65 000 euro. "
        "Bank minimum cash 50k euro. Growth 0.5%. Capex 2.4 million."
    )
    nums = scan_description_numbers(desc)
    assert any(abs(n - 210_000) < 1 for n in nums)
    assert any(abs(n - 65_000) < 1 for n in nums)
    assert any(abs(n - 50_000) < 1 for n in nums)
    assert any(abs(n - 0.005) < 1e-9 for n in nums)
    assert any(abs(n - 2_400_000) < 1 for n in nums)


def test_value_grounding_ignores_quote_formatting() -> None:
    desc = "Monthly revenue 210,000 euro. Starting cash 65,000 euro."
    # Quote text differs from description formatting — must still pass.
    result = check_stated_values(
        description=desc,
        stated={
            "revenue_monthly_eur": "monthly revenue 210000 EUR",
            "starting_cash_eur": "starting cash €65000",
        },
        parameters={
            "revenue_monthly_eur": 210_000,
            "starting_cash_eur": 65_000,
        },
    )
    assert result.ok, result.error_text()


def test_clean_brackets_and_stated_null_warn() -> None:
    params = {
        "revenue_monthly_eur": "€[0]",
        "starting_cash_eur": 0,
        "covenant_min_cash_eur": None,
        "one_off_events": [],
    }
    stated = {
        "revenue_monthly_eur": "€[0]",
        "covenant_min_cash_eur": "bank minimum",
    }
    cleaned, stated_out, warnings = clean_extraction_output(
        params, stated, "A small machine shop. Cash is tight."
    )
    assert cleaned["revenue_monthly_eur"] is None
    assert cleaned["starting_cash_eur"] is None
    assert "revenue_monthly_eur" not in stated_out
    assert "covenant_min_cash_eur" not in stated_out
    assert any("null" in w or "bracket" in w for w in warnings)


def test_required_one_off_from_description() -> None:
    desc = (
        "Monthly revenue 210,000 euro. Starting cash 65,000 euro. "
        "Bank minimum cash 50,000 euro. "
        "One-off equipment outflow of 95,000 euro in month 5."
    )
    req = extract_required_one_offs(desc)
    assert len(req) == 1
    assert req[0]["amount_eur"] == 95_000
    assert req[0]["month_index"] == 5
    assert req[0]["direction"] == "outflow"

    issues = enforce_required_one_offs([], desc)
    assert issues
    assert "missing required one-off" in issues[0].message

    issues_ok = enforce_required_one_offs(
        [{"amount_eur": 95_000, "month_index": 5, "direction": "outflow"}],
        desc,
    )
    assert not issues_ok

    issues_dir = enforce_required_one_offs(
        [{"amount_eur": 95_000, "month_index": 5, "direction": "inflow"}],
        desc,
    )
    assert issues_dir
    assert "wrong direction" in issues_dir[0].message


def test_finalize_rejects_empty_one_off_when_description_requires() -> None:
    desc = (
        "Monthly revenue 210,000 euro. Starting cash 65,000 euro. "
        "Bank minimum cash 50,000 euro. "
        "One-off equipment outflow of 95,000 euro in month 5."
    )
    envelope = {
        "scenario_shape": "unspecified",
        "scenario_shape_quote": None,
        "stated": {
            "revenue_monthly_eur": "Monthly revenue 210,000 euro",
            "starting_cash_eur": "Starting cash 65,000 euro",
            "covenant_min_cash_eur": "Bank minimum cash 50,000 euro",
        },
        "parameters": {
            "revenue_monthly_eur": 210_000,
            "starting_cash_eur": 65_000,
            "covenant_min_cash_eur": 50_000,
            "growth_per_month_fraction": None,
            "dso_days": None,
            "dpo_days": None,
            "one_off_events": [],
            "industry": None,
            "company_size": None,
        },
    }
    _params, _changes, check = finalize_extracted_parameters(
        envelope,
        desc,
        industry="metal workshop (machine shop)",
        company_size="small",
        seed=42,
        months=12,
    )
    assert not check.ok
    assert "one_off" in check.error_text().casefold()

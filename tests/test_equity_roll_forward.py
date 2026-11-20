"""Equity roll-forward must hold; VR-04 continuity is blocking (not a soft warning)."""

from __future__ import annotations

from pathlib import Path

import pytest

from payloq_generator.answer_key import build_answer_key
from payloq_generator.engine import generate_pack, load_input
from payloq_generator.pipeline import run_generation
from payloq_validate.checks import validate_pack

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scenarios"


def _equity_breaks(pack) -> list[tuple[str, float, float, float]]:
    months = pack.monthly_reports.months
    breaks: list[tuple[str, float, float, float]] = []
    for i in range(1, len(months)):
        prev = months[i - 1].balance_sheet.equity_and_liabilities.equity
        cur = months[i].balance_sheet.equity_and_liabilities.equity
        net = months[i].income_statement.net_result
        expected = prev + net
        if abs(cur - expected) > 2.0:
            breaks.append((months[i].month, cur, expected, cur - expected))
    return breaks


@pytest.mark.parametrize(
    "scenario_id",
    ["cash_critical", "cash_turning_critical_later"],
)
def test_equity_rolls_forward_for_cash_scenarios(scenario_id: str) -> None:
    inp = load_input(SCENARIOS / scenario_id / "input.json")
    pack = generate_pack(inp, seed=42)
    assert not _equity_breaks(pack), _equity_breaks(pack)
    key = build_answer_key(pack)
    result = validate_pack(pack, answer_key=key)
    eq = [i for i in result.issues if i.code == "equity_continuity"]
    assert not eq, eq
    errors = [i for i in result.issues if i.severity == "error"]
    assert not errors, errors


@pytest.mark.parametrize(
    "scenario_id",
    ["cash_critical", "cash_turning_critical_later"],
)
def test_cash_scenario_pipeline_passes_with_equity_check(
    tmp_path: Path, scenario_id: str
) -> None:
    inp = load_input(SCENARIOS / scenario_id / "input.json")
    outcome = run_generation(inp, tmp_path / scenario_id, seed=42)
    assert outcome.ok, outcome.validation.issues
    eq = [i for i in outcome.validation.issues if i.code == "equity_continuity"]
    assert not eq


def test_equity_continuity_is_blocking_error() -> None:
    """Deliberately break roll-forward → VR-04 equity_continuity must fail the run."""
    inp = load_input(SCENARIOS / "cash_critical" / "input.json")
    pack = generate_pack(inp, seed=42)
    # Mutate month 2 equity away from prev + net
    m1 = pack.monthly_reports.months[1]
    m1.balance_sheet.equity_and_liabilities.equity = (
        m1.balance_sheet.equity_and_liabilities.equity - 12_500.0
    )
    # Keep BS arithmetic balanced so only continuity fires
    e = m1.balance_sheet.equity_and_liabilities
    e.other_current_liabilities = (
        m1.balance_sheet.assets.total_assets - e.equity - e.loans - e.payables
    )
    e.total_equity_and_liabilities = (
        e.equity + e.loans + e.payables + e.other_current_liabilities
    )

    result = validate_pack(pack)
    assert not result.ok
    eq = [i for i in result.issues if i.code == "equity_continuity"]
    assert eq, "expected blocking equity_continuity issue"
    assert all(i.severity == "error" for i in eq)
    assert all(i.rule_id == "VR-04" for i in eq)

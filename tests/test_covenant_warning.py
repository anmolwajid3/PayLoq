"""Covenant warning: month-end cash below the bank minimum is reported as a warning."""

from __future__ import annotations

from pathlib import Path

from payloq_generator.engine import generate_pack, load_input
from payloq_validate.checks import validate_pack

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scenarios"


def _covenant_issues(pack):
    return [i for i in validate_pack(pack).issues if i.code == "cash_below_covenant"]


def test_warning_when_cash_drops_below_covenant() -> None:
    inp = load_input(SCENARIOS / "cash_critical" / "input.json")
    inp.parameters_from_language_model.covenant_min_cash_eur = 10_000_000.0
    issues = _covenant_issues(generate_pack(inp, seed=42))
    assert issues and all(i.severity == "warning" for i in issues)


def test_no_warning_when_cash_stays_above_covenant() -> None:
    inp = load_input(SCENARIOS / "good" / "input.json")
    inp.parameters_from_language_model.covenant_min_cash_eur = 0.0
    assert not _covenant_issues(generate_pack(inp, seed=42))

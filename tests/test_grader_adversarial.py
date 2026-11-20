"""Adversarial fixtures: deliberately wrong answers must not score 1.0."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from payloq_benchmark.graders import (
    STUB_PERFECT_SCORE_MEANS_WIRING_ONLY,
    grade_interpretation,
    grade_probes,
)
from payloq_llm.adapters import StubLlmAdapter


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "benchmarks").is_dir() and (candidate / "pyproject.toml").exists():
            return candidate
    return Path.cwd()


def _fixtures() -> dict:
    path = _repo_root() / "benchmarks" / "adversarial_answers.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_stub_perfect_scores_are_wiring_only_flag() -> None:
    """Document that stub 1.0 on reading/interp proves harness wiring, not understanding."""
    assert STUB_PERFECT_SCORE_MEANS_WIRING_ONLY is True


def test_stub_echo_still_scores_high_by_construction() -> None:
    """Stub answers echo pack_summary — high scores only prove the pipeline is wired."""
    fx = _fixtures()
    summary = fx["pack_summary"]
    stub = StubLlmAdapter()

    answers = {
        pid: stub.answer_numeric_probe(pid, "q", summary)
        for pid in (
            "cash_end",
            "revenue_last",
            "mom_revenue_change",
            "first_negative_projection_week",
        )
    }
    probes = grade_probes(answers, summary)
    assert probes.score == pytest.approx(1.0)

    interp = stub.interpret_figures(
        "Miksi kassa muuttuu annetuilla luvuilla?",
        summary,
    )
    ig = grade_interpretation(interp, summary)
    assert ig.score == pytest.approx(1.0)
    assert ig.per_field["factual"] == 1.0
    assert ig.per_field["grounded"] == 1.0
    assert ig.per_field["no_invented_causes"] == 1.0
    assert ig.per_field["no_contradiction"] == 1.0


@pytest.mark.parametrize(
    "case_id",
    [
        "invented_causes_fraud",
        "invented_causes_konkurssissa",
        "wrong_figures",
        "contradictory_cash_already_negative",
        "contradictory_negative_week",
        "keyword_fluff_no_figures",
    ],
)
def test_adversarial_interpretation_cases_fail_rubric(case_id: str) -> None:
    fx = _fixtures()
    summary = fx["pack_summary"]
    case = next(c for c in fx["interpretation_cases"] if c["id"] == case_id)
    grade = grade_interpretation(case["answer"], summary)

    assert grade.score < 1.0, f"{case_id} must not score perfect"
    assert grade.score <= case["expect_max_overall"], (
        f"{case_id}: score {grade.score} > max {case['expect_max_overall']} "
        f"(per_field={grade.per_field}, notes={grade.notes})"
    )
    for field, expected in case["expect_per_field"].items():
        assert grade.per_field[field] == pytest.approx(expected), (
            f"{case_id}.{field}: got {grade.per_field[field]}, want {expected}; "
            f"notes={grade.notes}"
        )


def test_wrong_probe_answers_do_not_score_one() -> None:
    fx = _fixtures()
    summary = fx["pack_summary"]
    wrong = fx["wrong_probe_answers"]
    grade = grade_probes(wrong, summary)

    assert grade.score < 1.0
    assert grade.score < 0.25
    for pid, answer in wrong.items():
        assert grade.per_field[pid] < 1.0, f"{pid}={answer} must not score 1.0"
        assert grade.per_field[pid] <= 0.1, (
            f"{pid} wrong answer scored {grade.per_field[pid]} (want near 0)"
        )


def test_field_by_field_demo_matches_fixture_contract() -> None:
    """Sanity-check the Anmol-facing field-by-field demo block stays complete."""
    fx = _fixtures()
    demo = fx["field_by_field_demo"]
    fields = {step["field"] for step in demo["steps"]}
    assert "reading.cash_end" in fields
    assert "interpretation.no_invented_causes" in fields
    assert "interpretation.no_contradiction" in fields
    assert "interpretation.grounded / factual" in fields

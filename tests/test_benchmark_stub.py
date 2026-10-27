"""Phase 3 benchmark harness — stub path (no Ollama required)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from payloq_benchmark.config import BenchmarkConfig, parse_model_token
from payloq_benchmark.graders import (
    extract_first_number,
    grade_interpretation,
    grade_parameters,
    grade_probes,
)
from payloq_benchmark.runner import run_benchmark, run_benchmark_stub
from payloq_llm.adapters import StubLlmAdapter


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "scenarios").is_dir() and (candidate / "pyproject.toml").exists():
            return candidate
    return Path.cwd()


def test_parse_model_token() -> None:
    assert parse_model_token("stub").adapter == "stub"
    assert parse_model_token("ollama").model == "llama3.2:1b"
    assert parse_model_token("ollama:llama3.2:1b").id == "ollama:llama3.2:1b"
    assert parse_model_token("llama3.2:1b").adapter == "ollama"


def test_grade_parameters_perfect() -> None:
    key = {
        "monthly_revenue_start_eur": 200000,
        "monthly_revenue_growth": 0.008,
        "days_sales_outstanding": 40,
        "days_payables_outstanding": 32,
        "target_cash_at_end_eur": 330000,
        "special_investment_eur": 0,
        "cost_shares_of_revenue": {
            "materials": 0.37,
            "services": 0.08,
            "personnel": 0.34,
            "other": 0.15,
        },
        "partly_fixed_costs": False,
    }
    g = grade_parameters(key, key)
    assert g.score == pytest.approx(1.0)


def test_grade_probes_and_interpretation_stub_answers() -> None:
    summary = {
        "cash_end": 330000.0,
        "revenue_last": 210000.0,
        "mom_revenue_change": 1600.0,
        "first_negative_projection_week": None,
    }
    answers = {
        "cash_end": '{"value": 330000}',
        "revenue_last": '{"value": 210000}',
        "mom_revenue_change": '{"value": 1600}',
        "first_negative_projection_week": '{"value": null}',
    }
    pg = grade_probes(answers, summary)
    assert pg.score == pytest.approx(1.0)
    assert extract_first_number("kassa on 330000 euroa") == 330000.0

    text = (
        "Kassasaldo kauden lopussa on 330000. "
        "Ennuste ei mene negatiiviseksi annetuilla luvuilla."
    )
    ig = grade_interpretation(text, summary)
    assert ig.score >= 0.66
    assert ig.per_field["no_invented_causes"] == 1.0

    bad = "Cash dropped because of customer fraud and a bank freeze."
    bad_g = grade_interpretation(bad, summary)
    assert bad_g.per_field["no_invented_causes"] == 0.0


def test_bench_stub(tmp_path: Path) -> None:
    result = run_benchmark_stub(
        BenchmarkConfig(
            scenario_ids=["good", "weak"],
            models=["stub"],
            out_dir=tmp_path / "bench",
            write_spotcheck=False,
        )
    )
    assert result.summary["n_runs"] == 2
    assert (tmp_path / "bench" / "results.json").exists()
    assert all(r.parameter_score is not None for r in result.runs)
    assert all(r.reading_score is not None for r in result.runs)
    assert all(r.interpretation_score is not None for r in result.runs)


def test_run_benchmark_full_stub_matrix(tmp_path: Path) -> None:
    root = _repo_root()
    out = tmp_path / "bench_full"
    cfg = BenchmarkConfig(
        scenario_ids=["good", "weak", "cash_critical"],
        models=["stub"],
        out_dir=out,
        write_spotcheck=True,
        judge={"enabled": True, "adapter": "stub"},
    )

    result = run_benchmark(cfg, scenarios_root=root)
    assert result.summary["n_runs"] == 3
    assert (out / "results.json").exists()
    assert (out / "metrics.sqlite").exists()
    assert (out / "scorecard.json").exists()
    assert (out / "spotcheck.csv").exists()
    assert (out / "hardware.json").exists()

    payload = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "phase3"

    # Stub should score well on reading probes (exact values from pack_summary)
    for run in result.runs:
        assert run.reading_score is not None and run.reading_score >= 0.9
        assert run.interpretation_score is not None and run.interpretation_score >= 0.5
        assert run.rough_cost_eur is not None

    con = sqlite3.connect(out / "metrics.sqlite")
    n = con.execute("SELECT COUNT(*) FROM benchmark_runs").fetchone()[0]
    con.close()
    assert n == 3


def test_run_with_injected_stub_adapter(tmp_path: Path) -> None:
    result = run_benchmark_stub(
        BenchmarkConfig(
            scenario_ids=["cash_critical"],
            models=["stub"],
            out_dir=tmp_path / "inj",
            write_spotcheck=False,
        ),
        adapters={"stub": StubLlmAdapter()},
    )
    assert result.summary["n_runs"] == 1
    assert result.runs[0].scenario_id == "cash_critical"

"""Benchmark harness — stub path + scorecard export (no Ollama required)."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from payloq_benchmark.config import (
    BenchmarkConfig,
    cpu_shortlist_specs,
    expand_model_tokens,
    parse_model_token,
)
from payloq_benchmark.graders import (
    extract_first_number,
    grade_fi_quality,
    grade_interpretation,
    grade_parameters,
    grade_probes,
)
from payloq_benchmark.runner import run_benchmark, run_benchmark_stub
from payloq_benchmark.scorecard import fi_band_label
from payloq_llm.adapters import StubLlmAdapter
from payloq_llm.defaults import RECOMMENDED_CPU_MODELS, recommended_ollama_tags


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


def test_cpu_shortlist_includes_llama32_1b_and_optionals() -> None:
    tags = recommended_ollama_tags(include_optional=True)
    assert "llama3.2:1b" in tags
    assert "llama3.2:3b" in tags
    assert "qwen2.5:3b" in tags
    assert any(r.get("tier") == "recommended" for r in RECOMMENDED_CPU_MODELS)

    specs = expand_model_tokens(["shortlist"])
    ids = [s.id for s in specs]
    assert ids[0] == "stub"
    assert "ollama:llama3.2:1b" in ids
    assert len(ids) == 4

    rec_only = expand_model_tokens(["shortlist:recommended"])
    assert [s.id for s in rec_only] == ["stub", "ollama:llama3.2:1b"]

    assert len(cpu_shortlist_specs(include_optional=False)) == 2


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
    assert ig.per_field["fi_quality"] >= 0.75

    bad = "Cash dropped because of customer fraud and a bank freeze."
    bad_g = grade_interpretation(bad, summary)
    assert bad_g.per_field["no_invented_causes"] == 0.0


def test_fi_quality_band_en_only_vs_finnish() -> None:
    fi = grade_fi_quality(
        "Kassasaldo ennusteessa muuttuu koska avoimet laskut: 45000 euroa.",
        expected_language="fi",
    )
    assert fi.score >= 0.75
    assert fi_band_label(fi.score) == "high"

    en = grade_fi_quality(
        "The cash balance and the projection change because of the invoice timing and week three.",
        expected_language="fi",
    )
    assert en.score < 0.40
    assert fi_band_label(en.score) == "low"
    # Main interpretation can still be factual without FI — EN-only is not a hard fail.
    summary = {"cash_end": 45000.0, "first_negative_projection_week": 3}
    main = grade_interpretation(
        "Cash end is 45000 and the projection goes negative in week 3.",
        summary,
        language="fi",
    )
    assert main.per_field["factual"] == 1.0
    assert main.per_field["fi_quality"] < 0.40

    na = grade_fi_quality("Anything", expected_language="en")
    assert na.per_field["applicable"] == 0.0
    assert fi_band_label(None) == "n/a"


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
    assert all(r.fi_quality_score is not None for r in result.runs)


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
    assert (out / "scorecard.csv").exists()
    assert (out / "runs.csv").exists()
    assert (out / "spotcheck.csv").exists()
    assert (out / "hardware.json").exists()

    payload = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "phase7"

    scorecard = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
    assert "fi_band_legend" in scorecard
    assert scorecard["by_model"]

    with (out / "scorecard.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows and "avg_fi_quality" in rows[0]
    assert "fi_band" in rows[0]

    for run in result.runs:
        assert run.reading_score is not None and run.reading_score >= 0.9
        assert run.interpretation_score is not None and run.interpretation_score >= 0.5
        assert run.fi_quality_score is not None
        assert run.rough_cost_eur is not None

    con = sqlite3.connect(out / "metrics.sqlite")
    n = con.execute("SELECT COUNT(*) FROM benchmark_runs").fetchone()[0]
    cols = {r[1] for r in con.execute("PRAGMA table_info(benchmark_runs)").fetchall()}
    con.close()
    assert n == 3
    assert "fi_quality_score" in cols


def test_skip_ollama_when_unavailable(tmp_path: Path) -> None:
    """Live Ollama cells are skipped when the host is down; stub still runs."""
    root = _repo_root()
    out = tmp_path / "bench_skip"
    cfg = BenchmarkConfig(
        scenario_ids=["good"],
        models=["stub", "ollama:llama3.2:1b"],
        out_dir=out,
        write_spotcheck=False,
        skip_unavailable=True,
    )
    # Force unreachable host on the ollama cell
    cfg.models[1].host = "http://127.0.0.1:1"

    result = run_benchmark(cfg, scenarios_root=root)
    assert result.summary["n_runs"] == 1
    assert result.runs[0].model == "stub"
    skipped = result.summary["skipped_models"]
    assert len(skipped) == 1
    assert skipped[0]["model"] == "ollama:llama3.2:1b"
    assert (out / "scorecard.json").exists()


def test_matrix_cpu_config_loads() -> None:
    root = _repo_root()
    path = root / "benchmarks" / "matrix.cpu.json"
    assert path.exists()
    from payloq_benchmark.config import load_matrix_config

    cfg = load_matrix_config(path)
    assert cfg.skip_unavailable is True
    assert len(cfg.models) == 4
    assert cfg.models[1].model == "llama3.2:1b"


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


@pytest.mark.integration
def test_ollama_bench_live_optional(tmp_path: Path) -> None:
    """Skipped unless a local Ollama serves tags; otherwise runs recommended cell."""
    from payloq_llm.adapters import OllamaAdapter
    from payloq_llm.defaults import DEFAULT_OLLAMA_MODEL

    if not OllamaAdapter(model=DEFAULT_OLLAMA_MODEL).is_available():
        pytest.skip("Ollama not reachable at default host")

    root = _repo_root()
    out = tmp_path / "bench_live"
    cfg = BenchmarkConfig(
        scenario_ids=["cash_critical"],
        models=["stub", f"ollama:{DEFAULT_OLLAMA_MODEL}"],
        out_dir=out,
        write_spotcheck=False,
        skip_unavailable=True,
    )
    result = run_benchmark(cfg, scenarios_root=root)
    assert result.summary["n_runs"] >= 1
    assert (out / "scorecard.csv").exists()

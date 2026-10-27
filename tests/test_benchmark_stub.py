from pathlib import Path

from payloq_benchmark.runner import BenchmarkConfig, run_benchmark_stub


def test_bench_stub(tmp_path: Path) -> None:
    result = run_benchmark_stub(
        BenchmarkConfig(
            scenario_ids=["good", "weak"],
            models=["stub"],
            out_dir=tmp_path / "bench",
        )
    )
    assert result.summary["n_runs"] == 2
    assert (tmp_path / "bench" / "results.json").exists()

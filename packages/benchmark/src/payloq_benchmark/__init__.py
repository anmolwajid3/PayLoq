"""PayLoq benchmark harness — model matrix, graders, metrics / scorecard store."""

from payloq_benchmark.config import (
    BenchmarkConfig,
    ModelSpec,
    cpu_shortlist_specs,
    load_matrix_config,
)
from payloq_benchmark.runner import BenchmarkResult, ModelRunMetrics, run_benchmark, run_benchmark_stub
from payloq_benchmark.scorecard import fi_band_label, write_scorecard_csv, write_scorecard_json

__all__ = [
    "BenchmarkConfig",
    "BenchmarkResult",
    "ModelRunMetrics",
    "ModelSpec",
    "cpu_shortlist_specs",
    "fi_band_label",
    "load_matrix_config",
    "run_benchmark",
    "run_benchmark_stub",
    "write_scorecard_csv",
    "write_scorecard_json",
]

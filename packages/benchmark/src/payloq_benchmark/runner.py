"""Phase 3 scaffold: model matrix runner + graders (stubbed metrics)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from payloq_llm.adapters import LlmAdapter, get_adapter


@dataclass
class BenchmarkConfig:
    scenario_ids: list[str] = field(default_factory=lambda: ["good", "weak", "cash_critical"])
    models: list[str] = field(default_factory=lambda: ["stub"])
    out_dir: Path = Path("runs/benchmark")


@dataclass
class ModelRunMetrics:
    model: str
    scenario_id: str
    latency_ms: float
    tokens_in: int | None
    tokens_out: int | None
    hardware: str
    parameter_score: float | None
    interpretation_score: float | None
    notes: str = ""


@dataclass
class BenchmarkResult:
    runs: list[ModelRunMetrics]
    summary: dict[str, Any]

    def write(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "runs": [asdict(r) for r in self.runs],
            "summary": self.summary,
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path


def grade_parameters(predicted: dict[str, Any], key: dict[str, Any], *, tol: float = 0.05) -> float:
    """Simple relative-error grader for numeric parameters (0..1)."""
    keys = [
        "monthly_revenue_start_eur",
        "monthly_revenue_growth",
        "days_sales_outstanding",
        "days_payables_outstanding",
        "target_cash_at_end_eur",
    ]
    scores: list[float] = []
    for k in keys:
        if k not in predicted or k not in key:
            continue
        p, t = float(predicted[k]), float(key[k])
        denom = max(abs(t), 1e-6)
        err = abs(p - t) / denom
        scores.append(max(0.0, 1.0 - err / max(tol * 10, 1e-6)))
    return sum(scores) / len(scores) if scores else 0.0


def run_benchmark_stub(
    config: BenchmarkConfig,
    *,
    parameter_keys: dict[str, dict[str, Any]] | None = None,
    adapters: dict[str, LlmAdapter] | None = None,
) -> BenchmarkResult:
    """
    Scaffold runner: exercises adapters without requiring GPU/Ollama.

    Real Phase 3 will load prompt packs, call local models, and fill latency/tokens.
    """
    parameter_keys = parameter_keys or {}
    adapters = adapters or {m: get_adapter("stub" if m == "stub" else m) for m in config.models}
    runs: list[ModelRunMetrics] = []

    for model in config.models:
        adapter = adapters.get(model) or get_adapter("stub")
        for sid in config.scenario_ids:
            t0 = time.perf_counter()
            # Stub prompt → params
            predicted = adapter.extract_parameters(
                f"skenaario {sid}",
                f"scenario {sid}",
                {"scenario_id": sid, "months": 12, "language": "fi", "currency": "EUR"},
            )
            latency = (time.perf_counter() - t0) * 1000
            key = parameter_keys.get(sid)
            score = grade_parameters(predicted, key) if key else None
            interp = adapter.interpret_figures(
                "Miksi kassa muuttuu? / Why does cash change?",
                {"scenario_id": sid, "cash_end": predicted.get("target_cash_at_end_eur")},
            )
            runs.append(
                ModelRunMetrics(
                    model=model,
                    scenario_id=sid,
                    latency_ms=round(latency, 3),
                    tokens_in=None,
                    tokens_out=None,
                    hardware="cpu",
                    parameter_score=score,
                    interpretation_score=1.0 if "stub" in interp.lower() or len(interp) > 20 else 0.0,
                    notes="Phase 1 scaffold — wire real model matrix in Phase 3",
                )
            )

    summary = {
        "n_runs": len(runs),
        "models": config.models,
        "scenarios": config.scenario_ids,
        "status": "scaffold",
    }
    result = BenchmarkResult(runs=runs, summary=summary)
    result.write(Path(config.out_dir) / "results.json")
    return result

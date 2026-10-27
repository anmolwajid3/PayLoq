"""Latency, tokens, hardware notes, and rough local-run cost estimates."""

from __future__ import annotations

import platform
import sys
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CallMetrics:
    """Metrics for a single LLM call."""

    latency_ms: float = 0.0
    tokens_in: int | None = None
    tokens_out: int | None = None
    model: str | None = None
    adapter: str | None = None
    error: str | None = None

    def merge(self, other: CallMetrics | None) -> CallMetrics:
        if other is None:
            return self
        tokens_in = _sum_optional(self.tokens_in, other.tokens_in)
        tokens_out = _sum_optional(self.tokens_out, other.tokens_out)
        return CallMetrics(
            latency_ms=self.latency_ms + other.latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=other.model or self.model,
            adapter=other.adapter or self.adapter,
            error=other.error or self.error,
        )


def _sum_optional(a: int | None, b: int | None) -> int | None:
    if a is None and b is None:
        return None
    return (a or 0) + (b or 0)


@dataclass
class HardwareNotes:
    """Portable hardware fingerprint for scorecards (CPU-first PoC)."""

    platform: str = field(default_factory=lambda: platform.platform())
    python: str = field(default_factory=lambda: sys.version.split()[0])
    processor: str = field(default_factory=lambda: platform.processor() or platform.machine())
    machine: str = field(default_factory=lambda: platform.machine())
    note: str = "CPU-friendly local workstation (PayLoq PoC)"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def short(self) -> str:
        return f"{self.machine}/{self.processor or 'cpu'} · py{self.python}"


# Rough local-electricity heuristic — not cloud API pricing.
# Tunable via BenchmarkConfig.cost_eur_per_1k_tokens.
DEFAULT_COST_EUR_PER_1K_TOKENS = {
    "stub": 0.0,
    "ollama": 0.00005,  # tiny local energy proxy for small CPU models
}


def estimate_cost_eur(
    *,
    adapter: str,
    tokens_in: int | None,
    tokens_out: int | None,
    latency_ms: float,
    cost_eur_per_1k_tokens: float | None = None,
    cost_eur_per_hour_idle: float = 0.02,
) -> float:
    """
    Rough cost-effectiveness proxy for local runs.

    Combines a per-token energy proxy with a wall-clock electricity share.
    """
    total_tokens = (tokens_in or 0) + (tokens_out or 0)
    rate = (
        cost_eur_per_1k_tokens
        if cost_eur_per_1k_tokens is not None
        else DEFAULT_COST_EUR_PER_1K_TOKENS.get(adapter, DEFAULT_COST_EUR_PER_1K_TOKENS["ollama"])
    )
    token_cost = (total_tokens / 1000.0) * rate
    hour_cost = (max(latency_ms, 0.0) / 3_600_000.0) * cost_eur_per_hour_idle
    return round(token_cost + hour_cost, 8)

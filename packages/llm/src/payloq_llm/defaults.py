"""Documented defaults for local LLM runs (CPU-friendly)."""

from __future__ import annotations

import os
from typing import Any

# Default from config / pilot work-order fix (override with --ollama-model / PAYLOQ_OLLAMA_MODEL).
# Pull: `ollama pull qwen2.5:7b`
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
# CPU-first param extraction (esp. Mac Docker) often needs >120s for tiny models.
# Override with PAYLOQ_OLLAMA_TIMEOUT / OLLAMA_TIMEOUT; Compose ollama profile uses 600.
DEFAULT_TIMEOUT_S = 300


def resolve_ollama_timeout_s(explicit: float | None = None) -> float:
    """Resolve HTTP timeout seconds: explicit arg → env → DEFAULT_TIMEOUT_S."""
    if explicit is not None:
        return float(explicit)
    for key in ("PAYLOQ_OLLAMA_TIMEOUT", "OLLAMA_TIMEOUT"):
        raw = os.environ.get(key)
        if raw is None or not str(raw).strip():
            continue
        try:
            value = float(str(raw).strip())
        except ValueError:
            continue
        if value > 0:
            return value
    return float(DEFAULT_TIMEOUT_S)

# Official CPU-first shortlist for Anmol Desktop / PayLoq local PoC (PL-7).
# Default / recommended Task A model is qwen2.5:7b (TC-ABC / pilot header).
RECOMMENDED_CPU_MODELS: list[dict[str, Any]] = [
    {
        "id": "stub",
        "adapter": "stub",
        "tier": "baseline",
        "notes": "Always-on stub — no Ollama required (CI / offline / CLI).",
    },
    {
        "id": "ollama:qwen2.5:7b",
        "adapter": "ollama",
        "model": "qwen2.5:7b",
        "tier": "recommended",
        "approx_size": "~4.7 GB",
        "notes": "Default Task A extract model. Header must show qwen2.5:7b.",
        "fallback_stub": False,
    },
    {
        "id": "ollama:llama3.2:1b",
        "adapter": "ollama",
        "model": "llama3.2:1b",
        "tier": "optional",
        "approx_size": "~1.3 GB",
        "notes": "Smaller optional CPU-friendly live model.",
        "fallback_stub": True,
    },
    {
        "id": "ollama:qwen2.5:0.5b",
        "adapter": "ollama",
        "model": "qwen2.5:0.5b",
        "tier": "optional",
        "approx_size": "~400 MB",
        "notes": "Tiny CPU-friendly alternate for fast Mac Docker pulls.",
        "fallback_stub": True,
    },
    {
        "id": "ollama:llama3.2:3b",
        "adapter": "ollama",
        "model": "llama3.2:3b",
        "tier": "optional",
        "approx_size": "~2.0 GB",
        "notes": "Larger optional step-up when Desktop CPU has headroom.",
        "fallback_stub": True,
    },
    {
        "id": "ollama:qwen2.5:3b",
        "adapter": "ollama",
        "model": "qwen2.5:3b",
        "tier": "optional",
        "approx_size": "~1.9 GB",
        "notes": "Second optional size for multilingual / FI probe comparison.",
        "fallback_stub": True,
    },
]

# Tags suggested in the web UI / docs when Ollama is empty (excludes stub).
UI_SUGGESTED_OLLAMA_TAGS: list[str] = [
    "qwen2.5:7b",
    "llama3.2:1b",
    "qwen2.5:0.5b",
    "llama3.2:3b",
]

# PL-52 / PL-54 default Generate compare shortlist — size ladder + Task A default.
# Order: non-llama first (qwen), then llama size ladder. Finance-tuned when pulled.
DEFAULT_COMPARE_MODELS: list[str] = [
    "qwen2.5:3b",
    "qwen2.5:7b",
    "llama3.2:1b",
    "llama3.2:3b",
]

# Optional finance-tuned cell (EN-primary; FI band scored separately).
DEFAULT_COMPARE_FINANCE_MODEL = "FableForge-AI/nexus-finance:q4_k_m"

# LLM-as-judge for interpretation (Generate compare + PDF). Never stubbed.
# Prefer models that are NOT the pack model (work-order: separate judge).
# Multi-judge panel: every pulled tag from this list (≠ pack) scores each answer.
DEFAULT_JUDGE_MODEL = "qwen2.5:7b"
DEFAULT_JUDGE_MODELS: list[str] = [
    "qwen2.5:7b",
    "llama3.2:3b",
    "qwen2.5:3b",
    "llama3.2:1b",
    "qwen2.5:0.5b",
]
# Fallback order when the preferred judge equals the pack model or is missing.
JUDGE_FALLBACK_MODELS: list[str] = list(DEFAULT_JUDGE_MODELS)


def recommended_ollama_tags(*, include_optional: bool = True) -> list[str]:
    """Ollama tags from the CPU shortlist (excludes stub)."""
    tags: list[str] = []
    for row in RECOMMENDED_CPU_MODELS:
        if row.get("adapter") != "ollama":
            continue
        if not include_optional and row.get("tier") == "optional":
            continue
        tag = row.get("model")
        if isinstance(tag, str):
            tags.append(tag)
    return tags

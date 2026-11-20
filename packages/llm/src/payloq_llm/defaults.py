"""Documented defaults for local LLM runs (CPU-friendly)."""

from __future__ import annotations

import os
from typing import Any

# Small CPU-friendly default; override with --ollama-model.
# Pull: `ollama pull llama3.2:1b`
DEFAULT_OLLAMA_MODEL = "llama3.2:1b"
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
# Recommended always includes llama3.2:1b; larger tags are optional stretch pulls.
# Tiny tags (0.5b) are for Mac Docker CPU when larger pulls are slow.
RECOMMENDED_CPU_MODELS: list[dict[str, Any]] = [
    {
        "id": "stub",
        "adapter": "stub",
        "tier": "baseline",
        "notes": "Always-on stub — no Ollama required (CI / offline / CLI).",
    },
    {
        "id": "ollama:llama3.2:1b",
        "adapter": "ollama",
        "model": "llama3.2:1b",
        "tier": "recommended",
        "approx_size": "~1.3 GB",
        "notes": "Default CPU-friendly live model. Pull first on Desktop.",
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
    "llama3.2:1b",
    "qwen2.5:0.5b",
    "llama3.2:3b",
]


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

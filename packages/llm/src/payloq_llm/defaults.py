"""Documented defaults for local LLM runs (CPU-friendly)."""

from __future__ import annotations

from typing import Any

# Small CPU-friendly default; override with --ollama-model.
# Pull: `ollama pull llama3.2:1b`
DEFAULT_OLLAMA_MODEL = "llama3.2:1b"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_S = 120

# Official CPU-first shortlist for Anmol Desktop / PayLoq local PoC (PL-7).
# Recommended always includes llama3.2:1b; larger tags are optional stretch pulls.
RECOMMENDED_CPU_MODELS: list[dict[str, Any]] = [
    {
        "id": "stub",
        "adapter": "stub",
        "tier": "baseline",
        "notes": "Always-on stub — no Ollama required (CI / offline).",
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

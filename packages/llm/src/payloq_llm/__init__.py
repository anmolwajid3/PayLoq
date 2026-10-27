"""LLM adapters for PayLoq (stubs + optional Ollama)."""

from payloq_llm.adapters import (
    FallbackAdapter,
    LlmAdapter,
    OllamaAdapter,
    StubLlmAdapter,
    get_adapter,
    input_from_descriptions,
    input_from_text,
)
from payloq_llm.defaults import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    RECOMMENDED_CPU_MODELS,
    recommended_ollama_tags,
)

__all__ = [
    "DEFAULT_OLLAMA_HOST",
    "DEFAULT_OLLAMA_MODEL",
    "RECOMMENDED_CPU_MODELS",
    "FallbackAdapter",
    "LlmAdapter",
    "OllamaAdapter",
    "StubLlmAdapter",
    "get_adapter",
    "input_from_descriptions",
    "input_from_text",
    "recommended_ollama_tags",
]

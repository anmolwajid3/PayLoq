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
from payloq_llm.defaults import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_MODEL

__all__ = [
    "DEFAULT_OLLAMA_HOST",
    "DEFAULT_OLLAMA_MODEL",
    "FallbackAdapter",
    "LlmAdapter",
    "OllamaAdapter",
    "StubLlmAdapter",
    "get_adapter",
    "input_from_descriptions",
    "input_from_text",
]

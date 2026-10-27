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
from payloq_llm.chat_demo import (
    DEMO_PRESETS,
    ChatDemoResult,
    build_chat_figures,
    list_demo_presets,
    run_chat_demo,
)
from payloq_llm.defaults import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_MODEL

__all__ = [
    "DEFAULT_OLLAMA_HOST",
    "DEFAULT_OLLAMA_MODEL",
    "DEMO_PRESETS",
    "ChatDemoResult",
    "FallbackAdapter",
    "LlmAdapter",
    "OllamaAdapter",
    "StubLlmAdapter",
    "build_chat_figures",
    "get_adapter",
    "input_from_descriptions",
    "input_from_text",
    "list_demo_presets",
    "run_chat_demo",
]

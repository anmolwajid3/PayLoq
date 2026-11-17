"""LLM adapters for PayLoq (stubs + optional Ollama)."""

from payloq_llm.adapters import (
    FallbackAdapter,
    LlmAdapter,
    OllamaAdapter,
    StubLlmAdapter,
    get_adapter,
    input_from_descriptions,
    input_from_text,
    list_ollama_models,
)
from payloq_llm.chat_demo import (
    DEMO_PRESETS,
    ChatDemoResult,
    build_chat_figures,
    list_demo_presets,
    run_chat_demo,
)
from payloq_llm.defaults import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    RECOMMENDED_CPU_MODELS,
    UI_SUGGESTED_OLLAMA_TAGS,
    recommended_ollama_tags,
)
from payloq_llm.nl_quality import assess_nl_params

__all__ = [
    "DEFAULT_OLLAMA_HOST",
    "DEFAULT_OLLAMA_MODEL",
    "DEMO_PRESETS",
    "ChatDemoResult",
    "RECOMMENDED_CPU_MODELS",
    "UI_SUGGESTED_OLLAMA_TAGS",
    "FallbackAdapter",
    "LlmAdapter",
    "OllamaAdapter",
    "StubLlmAdapter",
    "assess_nl_params",
    "build_chat_figures",
    "get_adapter",
    "input_from_descriptions",
    "input_from_text",
    "list_demo_presets",
    "list_ollama_models",
    "recommended_ollama_tags",
    "run_chat_demo",
]

"""Documented defaults for local LLM runs (CPU-friendly)."""

# Small CPU-friendly default; override with --ollama-model.
# Pull: `ollama pull llama3.2:1b`
DEFAULT_OLLAMA_MODEL = "llama3.2:1b"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_S = 120

"""Ollama HTTP timeout config: defaults, env, Settings, soft retry."""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from payloq_llm.adapters import OllamaAdapter, _is_timeout_urlerror, get_adapter
from payloq_llm.defaults import DEFAULT_TIMEOUT_S, resolve_ollama_timeout_s


def test_default_timeout_is_at_least_300() -> None:
    assert DEFAULT_TIMEOUT_S >= 300


def test_resolve_ollama_timeout_explicit_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYLOQ_OLLAMA_TIMEOUT", "900")
    assert resolve_ollama_timeout_s(45) == 45.0


def test_resolve_ollama_timeout_from_payloq_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_TIMEOUT", raising=False)
    monkeypatch.setenv("PAYLOQ_OLLAMA_TIMEOUT", "600")
    assert resolve_ollama_timeout_s() == 600.0


def test_resolve_ollama_timeout_from_ollama_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAYLOQ_OLLAMA_TIMEOUT", raising=False)
    monkeypatch.setenv("OLLAMA_TIMEOUT", "480")
    assert resolve_ollama_timeout_s() == 480.0


def test_resolve_ollama_timeout_invalid_env_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAYLOQ_OLLAMA_TIMEOUT", "not-a-number")
    monkeypatch.delenv("OLLAMA_TIMEOUT", raising=False)
    assert resolve_ollama_timeout_s() == float(DEFAULT_TIMEOUT_S)


def test_ollama_adapter_reads_env_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYLOQ_OLLAMA_TIMEOUT", "600")
    adapter = OllamaAdapter(model="llama3.2:1b", host="http://127.0.0.1:9")
    assert adapter.timeout_s == 600.0


def test_get_adapter_passes_explicit_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYLOQ_OLLAMA_TIMEOUT", "600")
    adapter = get_adapter(
        "ollama",
        fallback_stub=False,
        model="llama3.2:1b",
        host="http://127.0.0.1:9",
        timeout_s=120,
    )
    assert isinstance(adapter, OllamaAdapter)
    assert adapter.timeout_s == 120.0


def test_settings_ollama_timeout_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYLOQ_OLLAMA_TIMEOUT", "600")
    from payloq_api.config import Settings, get_settings

    get_settings.cache_clear()
    try:
        settings = Settings()
        assert settings.ollama_timeout == 600.0
    finally:
        get_settings.cache_clear()


def test_is_timeout_urlerror_detects_wrapped_timeout() -> None:
    wrapped = urllib.error.URLError(TimeoutError("timed out"))
    assert _is_timeout_urlerror(wrapped) is True
    other = urllib.error.URLError(ConnectionRefusedError("refused"))
    assert _is_timeout_urlerror(other) is False


def test_chat_retries_once_on_timeout_then_succeeds() -> None:
    adapter = OllamaAdapter(
        model="llama3.2:1b",
        host="http://ollama:11434",
        timeout_s=12,
        http_timeout_retries=1,
    )
    ok_resp = MagicMock()
    ok_resp.read.return_value = b'{"message":{"content":"{\\"ok\\":true}"},"eval_count":1}'
    ok_resp.__enter__.return_value = ok_resp
    ok_resp.__exit__.return_value = False

    with patch("payloq_llm.adapters.urllib.request.urlopen") as urlopen:
        urlopen.side_effect = [
            TimeoutError("timed out"),
            ok_resp,
        ]
        out = adapter.chat("hi", json_mode=False)
    assert "ok" in out
    assert urlopen.call_count == 2


def test_chat_timeout_raises_after_retries() -> None:
    adapter = OllamaAdapter(
        model="llama3.2:1b",
        host="http://ollama:11434",
        timeout_s=12,
        http_timeout_retries=1,
    )
    with patch("payloq_llm.adapters.urllib.request.urlopen") as urlopen:
        urlopen.side_effect = TimeoutError("timed out")
        with pytest.raises(RuntimeError, match="timed out after 12"):
            adapter.chat("hi", json_mode=False)
    assert urlopen.call_count == 2

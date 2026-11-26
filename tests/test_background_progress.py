"""progress.json helpers for background Generate."""

from __future__ import annotations

from pathlib import Path

from payloq_api.schemas import GenerateFromTextRequest
from payloq_api.services.progress import load_progress, write_progress


def test_write_and_load_progress(tmp_path: Path):
    payload = write_progress(
        tmp_path,
        percent=42,
        stage="extract",
        label_en="Extracting…",
        label_fi="Poimitaan…",
    )
    assert payload["percent"] == 42
    assert (tmp_path / "progress.json").is_file()
    loaded = load_progress(tmp_path)
    assert loaded is not None
    assert loaded["stage"] == "extract"
    assert loaded["label_fi"] == "Poimitaan…"
    assert loaded["done"] is False


def test_progress_clamps_percent(tmp_path: Path):
    over = write_progress(
        tmp_path, percent=150, stage="done", label_en="Done", done=True
    )
    assert over["percent"] == 100
    under = write_progress(
        tmp_path, percent=-5, stage="queued", label_en="Queued"
    )
    assert under["percent"] == 0


def test_generate_from_text_background_default():
    body = GenerateFromTextRequest(
        text="Monthly revenue 250000 euro. Starting cash 150000.",
        llm="ollama",
        language="en",
        industry="retail",
        company_size="small",
        months=12,
    )
    assert body.background is True

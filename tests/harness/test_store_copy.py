"""The session hook must not abort pytest when the project store is absent."""

from __future__ import annotations

from pathlib import Path

from harness import report


def test_store_copy_skips_when_store_is_absent(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "no-such-store" / "docs"
    monkeypatch.setattr(report, "STORE_DOCS", missing)
    src = tmp_path / "harness_report.md"
    src.write_text("x", encoding="utf-8")
    report._copy_store(src, "harness_report.md")
    assert not missing.exists()


def test_store_copy_writes_when_store_exists(tmp_path: Path, monkeypatch) -> None:
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setattr(report, "STORE_DOCS", store / "docs")
    src = tmp_path / "harness_report.md"
    src.write_text("hello", encoding="utf-8")
    report._copy_store(src, "harness_report.md")
    assert (store / "docs" / "harness_report.md").read_text(encoding="utf-8") == "hello"

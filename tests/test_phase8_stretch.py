"""§4 stretch: chat demo (code figures + stub) and journal entries export."""

from __future__ import annotations

import json
from pathlib import Path

from payloq_generator.engine import generate_pack, load_input, write_pack
from payloq_generator.journal import build_journal_entries
from payloq_llm.chat_demo import DEMO_PRESETS, build_chat_figures, run_chat_demo
from payloq_validate.checks import validate_pack


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_journal_entries_balanced_and_written(tmp_path: Path):
    inp = load_input(_repo_root() / "scenarios" / "cash_critical" / "input.json")
    pack = generate_pack(inp, seed=42)
    journal = build_journal_entries(pack)
    assert journal.entries, "expected journal vouchers"
    for entry in journal.entries:
        debit = round(sum(line.debit for line in entry.lines), 2)
        credit = round(sum(line.credit for line in entry.lines), 2)
        assert abs(debit - credit) < 0.02

    out = tmp_path / "pack"
    write_pack(pack, out, write_xlsx=True, write_journal=True)
    assert (out / "journal_entries.json").is_file()
    data = json.loads((out / "journal_entries.json").read_text(encoding="utf-8"))
    assert data["entries"]
    # Phase 1 validators still green
    reloaded_ok = validate_pack(generate_pack(inp, seed=42))
    assert reloaded_ok.ok


def test_write_pack_no_journal_skips_file(tmp_path: Path):
    inp = load_input(_repo_root() / "scenarios" / "good" / "input.json")
    pack = generate_pack(inp, seed=42)
    out = tmp_path / "no_j"
    write_pack(pack, out, write_xlsx=False, write_journal=False)
    assert not (out / "journal_entries.json").exists()
    assert (out / "input.json").is_file()


def test_chat_demo_cash_negative_stub():
    inp = load_input(_repo_root() / "scenarios" / "cash_critical" / "input.json")
    pack = generate_pack(inp, seed=42)
    figures = build_chat_figures(pack)
    assert figures["first_negative_projection_week"] is not None
    assert figures["first_negative_projection_week"] <= 3

    result = run_chat_demo(
        pack,
        preset="cash_negative",
        language="fi",
        llm="stub",
    )
    assert result.preset == "cash_negative"
    assert result.question == DEMO_PRESETS["cash_negative"]["fi"]
    assert result.llm_adapter == "stub"
    assert "negatiiv" in result.answer.lower() or "negative" in result.answer.lower()
    assert result.figures["cash_end"] == figures["cash_end"]


def test_chat_demo_cash_drop_en():
    inp = load_input(_repo_root() / "scenarios" / "weak" / "input.json")
    pack = generate_pack(inp, seed=42)
    result = run_chat_demo(
        pack,
        preset="cash_drop",
        language="en",
        llm="stub",
    )
    assert result.question == DEMO_PRESETS["cash_drop"]["en"]
    assert "Cash at period end" in result.answer or "Kassasaldo" in result.answer
    assert "balance_history_change" in result.figures


def test_chat_demo_custom_question():
    inp = load_input(_repo_root() / "scenarios" / "good" / "input.json")
    pack = generate_pack(inp, seed=42)
    result = run_chat_demo(
        pack,
        question="When does cash go negative?",
        language="en",
        llm="stub",
    )
    assert result.figures["first_negative_projection_week"] is None
    assert "non-negative" in result.answer.lower() or "ei mene" in result.answer.lower()

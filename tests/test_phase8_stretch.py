"""§4 stretch: chat demo (code figures + stub)."""

from __future__ import annotations

import json
from pathlib import Path

from payloq_generator.engine import generate_pack, load_input, write_pack
from payloq_llm.chat_demo import (
    DEMO_PRESETS,
    build_chat_figures,
    run_chat_demo,
    suggest_followup_questions,
)
from payloq_validate.checks import validate_pack


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_write_pack_never_emits_journal(tmp_path: Path):
    inp = load_input(_repo_root() / "scenarios" / "good" / "input.json")
    pack = generate_pack(inp, seed=42)
    out = tmp_path / "with_xlsx"
    write_pack(pack, out, write_xlsx=True)
    assert not (out / "journal_entries.json").exists()
    reloaded_ok = validate_pack(generate_pack(inp, seed=42), check_fidelity=False)
    assert reloaded_ok.ok


def test_write_pack_no_journal_skips_file(tmp_path: Path):
    inp = load_input(_repo_root() / "scenarios" / "good" / "input.json")
    pack = generate_pack(inp, seed=42)
    out = tmp_path / "no_j"
    write_pack(pack, out, write_xlsx=False)
    assert not (out / "journal_entries.json").exists()
    assert (out / "input.json").is_file()


def test_chat_demo_cash_negative_stub():
    inp = load_input(_repo_root() / "scenarios" / "cash_critical" / "input.json")
    pack = generate_pack(inp, seed=42)
    figures = build_chat_figures(pack)
    assert figures["first_negative_projection_week"] is not None
    assert figures["first_negative_projection_week"] <= 3
    assert figures["first_negative_date"] == figures["first_negative_projection_week_end"]
    assert figures["first_negative_balance"] == figures["first_negative_projection_balance"]
    assert figures["currency"] == "EUR"
    assert figures["projection_negative_crossings"]
    assert figures["projection_negative_crossings"][0]["week"] == figures[
        "first_negative_projection_week"
    ]

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
    # Must cite this run's date + amount — never a glossary-style definition.
    assert figures["first_negative_date"] in result.answer
    bal = figures["first_negative_balance"]
    assert bal is not None
    assert str(int(bal)) in result.answer.replace(",", "").replace(" ", "")
    assert "when the balance history change is negative" not in result.answer.lower()
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
    hist = result.figures["balance_history_change"]
    assert hist is not None
    assert str(int(hist)) in result.answer.replace(",", "").replace(" ", "")
    assert "when the balance history change is negative" not in result.answer.lower()


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
    assert result.figures["first_negative_date"] is None
    low = result.answer.lower()
    assert "not show cash going negative" in low or "ei mene negatiiviseksi" in low
    assert "330000" in result.answer.replace(",", "").replace(" ", "")


def test_suggest_followups_refresh_after_prior_questions():
    inp = load_input(_repo_root() / "scenarios" / "cash_critical" / "input.json")
    pack = generate_pack(inp, seed=42)
    figures = build_chat_figures(pack)

    seed = suggest_followup_questions(figures, language="fi", prior_questions=[])
    assert seed[0]["id"] == "cash_drop"
    assert seed[1]["id"] == "cash_negative"
    assert all("question" in row for row in seed)

    after_drop = suggest_followup_questions(
        figures,
        language="en",
        prior_questions=[DEMO_PRESETS["cash_drop"]["en"]],
    )
    ids = [row["id"] for row in after_drop]
    assert "cash_drop" not in ids
    assert "cash_negative" in ids
    # Figure-gated follow-ups appear once seeds are consumed / skipped.
    assert any(i != "cash_negative" for i in ids)

    after_both = suggest_followup_questions(
        figures,
        language="fi",
        prior_questions=[
            DEMO_PRESETS["cash_drop"]["fi"],
            DEMO_PRESETS["cash_negative"]["fi"],
        ],
    )
    after_ids = {row["id"] for row in after_both}
    assert "cash_drop" not in after_ids
    assert "cash_negative" not in after_ids
    assert after_both, "expected figure-based follow-ups after seed presets"
    assert all(row["question"] for row in after_both)


def test_interpretation_prompt_forbids_definitions():
    from payloq_llm.prompts import INTERPRETATION_SYSTEM, interpretation_prompt

    prompt = interpretation_prompt(
        "When does cash go negative?",
        {
            "first_negative_date": "2026-11-21",
            "first_negative_balance": -41807.0,
            "currency": "EUR",
        },
    )
    assert "NEVER define" in prompt
    assert "first_negative_date" in prompt
    assert "balance history change is negative" in prompt.lower()
    assert "Figures JSON" in prompt
    assert "Only interpret" in INTERPRETATION_SYSTEM or "ONLY interpret" in INTERPRETATION_SYSTEM

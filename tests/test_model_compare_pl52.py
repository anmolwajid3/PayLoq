"""PL-52 multi-model compare helpers (graders on a code-built pack)."""

from __future__ import annotations

from pathlib import Path

import pytest

from payloq_api.services.model_compare import (
    resolve_compare_models,
    resolve_judge_model,
    run_model_comparison,
    score_model_on_pack,
)
from payloq_benchmark.pack_summary import build_pack_summary
from payloq_generator.engine import generate_pack, load_input
from payloq_llm.adapters import StubLlmAdapter
from payloq_llm.defaults import DEFAULT_COMPARE_MODELS


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_default_compare_shortlist_size_ladder() -> None:
    assert "llama3.2:1b" in DEFAULT_COMPARE_MODELS
    assert "llama3.2:3b" in DEFAULT_COMPARE_MODELS
    assert "qwen2.5:3b" in DEFAULT_COMPARE_MODELS
    assert "qwen2.5:7b" in DEFAULT_COMPARE_MODELS
    assert "stub" not in DEFAULT_COMPARE_MODELS


def test_resolve_compare_models_includes_primary_and_dedupes() -> None:
    tags = resolve_compare_models(
        requested=["qwen2.5:3b", "qwen2.5:3b", "llama3.2:3b"],
        primary="qwen2.5:7b",
        available_only=False,
    )
    assert tags[0] == "qwen2.5:7b"
    assert tags.count("qwen2.5:3b") == 1
    assert "stub" not in tags


def test_resolve_judge_model_skips_pack_self_judge() -> None:
    assert resolve_judge_model(
        pulled=["qwen2.5:7b", "llama3.2:3b"],
        pack_model="qwen2.5:7b",
    ) == "llama3.2:3b"
    assert resolve_judge_model(pulled=["qwen2.5:7b"], pack_model="qwen2.5:7b") is None


def test_score_stub_on_preset_pack(tmp_path: Path) -> None:
    root = _repo_root()
    inp = load_input(root / "scenarios" / "cash_critical" / "input.json")
    pack = generate_pack(inp, seed=42)
    summary = build_pack_summary(pack)
    key = pack.input.parameters_from_language_model.model_dump()
    adapter = StubLlmAdapter(preset=pack.input.parameters_from_language_model)
    row = score_model_on_pack(
        adapter=adapter,
        model="stub-test",
        description_fi=inp.scenario_description.fi,
        description_en=inp.scenario_description.en,
        options=inp.options.model_dump(),
        parameter_key=key,
        pack_summary=summary,
        language="fi",
    )
    assert row["parameter_score"] == pytest.approx(1.0)
    assert row["reading_score"] == pytest.approx(1.0)
    assert row["mom_score"] == pytest.approx(1.0)
    assert row["interpretation_score"] == pytest.approx(1.0)
    assert row["composite_score"] > 0.9


def test_run_model_comparison_writes_artifact(tmp_path: Path) -> None:
    """Injected path: skip Ollama by scoring only via direct stub call above;
    here ensure empty models list still writes a valid payload shape."""
    root = _repo_root()
    inp = load_input(root / "scenarios" / "good" / "input.json")
    pack = generate_pack(inp, seed=42)
    out = tmp_path / "run_cmp"
    payload = run_model_comparison(
        pack=pack,
        text=inp.scenario_description.fi,
        language="fi",
        options=inp.options.model_dump(),
        models=[],  # no live ollama cells
        pack_model="qwen2.5:7b",
        out_dir=out,
    )
    assert (out / "comparison.json").exists()
    assert payload["pack_model"] == "qwen2.5:7b"
    assert payload["models"] == []
    assert payload["recommended_model"] is None
    assert "judge_role" in payload
    assert "score_weights" in payload

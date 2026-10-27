"""§4 chat demo over a stored generation run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from payloq_api.config import Settings
from payloq_api.models import GenerationRun
from payloq_llm.chat_demo import ChatDemoResult, list_demo_presets, run_chat_demo
from payloq_llm.defaults import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_MODEL
from payloq_schemas.models import (
    CashAndInvoices,
    GeneratorInput,
    JournalEntries,
    MonthlyReports,
    ScenarioPack,
)


def load_pack_from_run(run: GenerationRun) -> ScenarioPack:
    if not run.artifact_dir:
        raise FileNotFoundError("Run has no artifact directory")
    root = Path(run.artifact_dir)
    pack = ScenarioPack(
        input=GeneratorInput.model_validate_json(
            (root / "input.json").read_text(encoding="utf-8")
        ),
        monthly_reports=MonthlyReports.model_validate_json(
            (root / "monthly_reports.json").read_text(encoding="utf-8")
        ),
        cash_and_invoices=CashAndInvoices.model_validate_json(
            (root / "cash_and_invoices.json").read_text(encoding="utf-8")
        ),
    )
    journal_path = root / "journal_entries.json"
    if journal_path.is_file():
        pack = pack.model_copy(
            update={
                "journal_entries": JournalEntries.model_validate_json(
                    journal_path.read_text(encoding="utf-8")
                )
            }
        )
    return pack


def chat_on_run(
    run: GenerationRun,
    settings: Settings,
    *,
    question: str | None = None,
    preset: str | None = None,
    language: str = "fi",
    llm: str = "stub",
    ollama_model: str | None = None,
    ollama_host: str | None = None,
    no_fallback_stub: bool = False,
) -> ChatDemoResult:
    pack = load_pack_from_run(run)
    return run_chat_demo(
        pack,
        question=question,
        preset=preset,
        language=language,
        llm=llm,
        ollama_model=ollama_model or settings.ollama_model or DEFAULT_OLLAMA_MODEL,
        ollama_host=ollama_host or settings.ollama_host or DEFAULT_OLLAMA_HOST,
        no_fallback_stub=no_fallback_stub,
    )


def demo_presets_payload(language: str = "fi") -> list[dict[str, str]]:
    return list_demo_presets(language)


def result_to_dict(result: ChatDemoResult) -> dict[str, Any]:
    return {
        "question": result.question,
        "answer": result.answer,
        "figures": result.figures,
        "preset": result.preset,
        "llm_adapter": result.llm_adapter,
        "fallback_note": result.fallback_note,
        "metrics": result.metrics,
    }


def ensure_journal_artifact(run: GenerationRun) -> Path:
    """Build journal_entries.json for an existing run if missing."""
    from payloq_generator.journal import build_journal_entries

    pack = load_pack_from_run(run)
    if pack.journal_entries is None:
        pack = pack.model_copy(update={"journal_entries": build_journal_entries(pack)})
    assert run.artifact_dir
    path = Path(run.artifact_dir) / "journal_entries.json"
    path.write_text(pack.journal_entries.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path

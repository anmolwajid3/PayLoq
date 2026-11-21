"""Run one scenario through the same functions the API generate path calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from payloq_generator.pipeline import run_generation
from payloq_llm.adapters import (
    LlmAdapter,
    OllamaAdapter,
    StubLlmAdapter,
    default_options_from_text,
    input_from_text,
)
from payloq_llm.defaults import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_MODEL

from harness.adapter import FixtureAdapter
from harness.caches import clear_module_caches
from harness.checks import Failure, evaluate_case
from harness.scenarios import Case, build_case

LIVE_MODEL = DEFAULT_OLLAMA_MODEL  # qwen2.5:7b


@dataclass
class CellResult:
    scenario: str
    seed: int
    failures: list[Failure] = field(default_factory=list)
    model: str | None = None
    raw_json: str | None = None

    @property
    def label(self) -> str:
        names: list[str] = []
        for item in self.failures:
            if item.check not in names:
                names.append(item.check)
        return "PASS" if not names else ", ".join(names)


def _adapter_for(case: Case, *, live: bool) -> LlmAdapter:
    if live:
        return OllamaAdapter(model=LIVE_MODEL, host=DEFAULT_OLLAMA_HOST, timeout_s=600)
    adapter = FixtureAdapter()
    adapter.bind(case.extraction)
    return adapter


def generate_once(
    case: Case, out_dir: Path, *, live: bool
) -> tuple[str | None, str | None, str | None]:
    """One generation into a fresh directory. Returns (error, model, raw json)."""
    clear_module_caches()
    adapter = _adapter_for(case, live=live)
    opts = default_options_from_text(
        industry=case.industry,
        company_size=case.company_size,
        months=case.months,
        language=case.language,
        scenario_id=case.scenario_id,
        as_of="2026-10-31",
    )
    # run_from_text passes seed to run_generation but not into extraction options.
    # Both functions accept it; the harness supplies it so each seed is the run seed.
    opts["seed"] = case.seed
    model = getattr(adapter, "model", None) or adapter.name
    try:
        inp = input_from_text(
            text=case.text,
            adapter=adapter,
            language=case.language,
            options=opts,
            with_invoice_texts=True,
        )
        outcome = run_generation(
            inp,
            out_dir,
            seed=case.seed,
            write_xlsx=False,
            raw_llm_output=getattr(adapter, "last_raw_output", None),
            llm_name=str(model),
        )
    except Exception as exc:  # noqa: BLE001 — the harness records the failure, it does not fix it
        return str(exc), str(model), getattr(adapter, "last_raw_output", None)
    raw = getattr(adapter, "last_raw_output", None)
    if not (out_dir / "input.json").is_file():
        return outcome.error_message or "output files were not written", str(model), raw
    return None, str(model), raw


def run_cell_in(
    parent: Path, scenario: str, seed: int, *, live: bool, templates: dict[str, Any]
) -> CellResult:
    case = build_case(scenario, seed, templates)
    out_a = parent / "run_a"
    out_b = parent / "run_b"
    err_a, model, raw = generate_once(case, out_a, live=live)
    generate_once(case, out_b, live=live)
    failures = evaluate_case(case, out_a, out_b, call_error=err_a, templates=templates)
    return CellResult(scenario=scenario, seed=seed, failures=failures, model=model, raw_json=raw)


def run_check_g(parent: Path) -> list[CellResult]:
    """Check G: keyword stub is rejected, and a dead Ollama host writes no data files."""
    import payloq_api.models  # noqa: F401 — register tables
    from payloq_api.config import Settings
    from payloq_api.services.generate import run_from_text
    from sqlmodel import Session, SQLModel, create_engine

    clear_module_caches()
    cells: list[CellResult] = []

    stub_failures: list[Failure] = []
    try:
        input_from_text(
            text="A small machine shop.",
            adapter=StubLlmAdapter(),
            language="en",
            options=default_options_from_text(language="en"),
        )
        stub_failures.append(
            Failure(
                check="stub",
                expected="input_from_text rejects the keyword stub",
                actual="input_from_text accepted StubLlmAdapter",
                file="input.json",
            )
        )
    except ValueError as exc:
        if "stub" not in str(exc).lower() and "ollama" not in str(exc).lower():
            stub_failures.append(
                Failure(
                    check="stub",
                    expected="rejection that names the stub or requires Ollama",
                    actual=str(exc),
                    file="input.json",
                )
            )
    except Exception as exc:  # noqa: BLE001
        stub_failures.append(
            Failure(
                check="stub",
                expected="ValueError rejecting the stub",
                actual=f"{type(exc).__name__}: {exc}",
                file="input.json",
            )
        )

    stub_dir = parent / "stub"
    stub_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(
        artifact_dir=stub_dir,
        database_url="sqlite://",
        ollama_host="http://127.0.0.1:9",
        ollama_timeout=3,
    )
    with Session(engine) as session:
        run = run_from_text(
            session,
            settings,
            text="A small machine shop, cash is tight now.",
            llm="stub",
            language="en",
            seed=1,
            write_xlsx=False,
        )
    written = _data_files(stub_dir)
    if run.status != "error":
        stub_failures.append(
            Failure(
                check="stub",
                expected="run_from_text status error",
                actual=f"status {run.status} error={run.error_message}",
                file="input.json",
            )
        )
    if written:
        stub_failures.append(
            Failure(
                check="stub",
                expected="no input/monthly/cash/answer_key files",
                actual="wrote " + ", ".join(written),
                file=written[0],
            )
        )
    cells.append(CellResult(scenario="stub", seed=1, failures=stub_failures, model=None))

    dead_dir = parent / "unreachable"
    dead_dir.mkdir(parents=True, exist_ok=True)
    clear_module_caches()
    dead_settings = Settings(
        artifact_dir=dead_dir,
        database_url="sqlite://",
        ollama_host="http://127.0.0.1:9",
        ollama_timeout=3,
        ollama_model=LIVE_MODEL,
    )
    unreachable_failures: list[Failure] = []
    with Session(engine) as session:
        run = run_from_text(
            session,
            dead_settings,
            text="A small machine shop with monthly revenue 120000 euro.",
            llm="ollama",
            language="en",
            seed=1,
            write_xlsx=False,
            ollama_host="http://127.0.0.1:9",
            ollama_model=LIVE_MODEL,
        )
    written = _data_files(dead_dir)
    if run.status != "error":
        unreachable_failures.append(
            Failure(
                check="ollama-unreachable",
                expected="status error when Ollama is unreachable",
                actual=f"status {run.status} error={run.error_message}",
                file="input.json",
            )
        )
    if written:
        unreachable_failures.append(
            Failure(
                check="ollama-unreachable",
                expected="no data files when Ollama is unreachable",
                actual="wrote " + ", ".join(written),
                file=written[0],
            )
        )
    message = (run.error_message or "").lower()
    if "stub:" in message or "heuristic" in message:
        unreachable_failures.append(
            Failure(
                check="ollama-unreachable",
                expected="error reason without a keyword-stub fallback",
                actual=run.error_message or "",
                file="input.json",
            )
        )
    cells.append(
        CellResult(
            scenario="ollama-unreachable",
            seed=1,
            failures=unreachable_failures,
            model=LIVE_MODEL,
        )
    )
    return cells


def _data_files(root: Path) -> list[str]:
    names = {"input.json", "monthly_reports.json", "cash_and_invoices.json", "answer_key.json"}
    found: list[str] = []
    if not root.exists():
        return found
    for path in root.rglob("*"):
        if path.is_file() and path.name in names:
            found.append(path.name)
    return sorted(set(found))

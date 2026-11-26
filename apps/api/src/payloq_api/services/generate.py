"""Wire existing generator / LLM / validate packages into API runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlmodel import Session

from payloq_api.config import Settings
from payloq_api.models import GenerationRun, Scenario
from payloq_generator.engine import load_input
from payloq_generator.pipeline import run_generation
from payloq_llm.adapters import (
    default_options_from_text,
    get_adapter,
    input_from_text,
)
from payloq_llm.defaults import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_MODEL
from payloq_llm.nl_quality import assess_nl_params
from payloq_schemas.field_map import build_field_summary_rows
from payloq_schemas.models import GeneratorInput, ScenarioPack


def _pack_summary(
    pack: ScenarioPack,
    *,
    nl_soft_warnings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    cash = pack.cash_and_invoices
    months = pack.monthly_reports.months
    last = months[-1] if months else None
    projection = cash.projection_from_open_invoices
    params = pack.input.parameters_from_language_model
    options = pack.input.options.model_dump()
    lang = getattr(pack.input.options, "language", None) or "fi"
    params_dict = params.model_dump()
    return {
        "scenario": pack.input.options.scenario_id or pack.input.meta.scenario,
        "months": len(months),
        "as_of": cash.meta.as_of,
        "last_cash": last.balance_sheet.assets.cash if last else None,
        "last_revenue": last.income_statement.revenue if last else None,
        "open_invoices": len(cash.open_invoices),
        "balance_history": [
            {"week": p.week, "date": p.date, "balance": p.balance}
            for p in cash.balance_history
        ],
        "projection": [
            {
                "week": w.week,
                "week_end": w.week_end,
                "sales_inflow": w.sales_inflow,
                "purchase_outflow": w.purchase_outflow,
                "projected_balance": w.projected_balance,
            }
            for w in projection
        ],
        "description": pack.input.scenario_description.model_dump(),
        "language": lang,
        "options": options,
        "parameters": params_dict,
        # Driven solely by packages/schemas/.../field_map.json (generic display).
        "field_summary": build_field_summary_rows(
            params=params_dict, options=options, lang=str(lang)
        ),
        "nl_soft_warnings": nl_soft_warnings or [],
    }


def _list_artifacts(out_dir: Path) -> list[str]:
    if not out_dir.exists():
        return []
    return sorted(p.name for p in out_dir.iterdir() if p.is_file())


def run_preset(
    session: Session,
    settings: Settings,
    *,
    scenario: Scenario,
    seed: int = 42,
    write_xlsx: bool = True,
) -> GenerationRun:
    run = GenerationRun(
        scenario_id=scenario.id,
        source="preset",
        llm_adapter="none",
        seed=seed,
        status="pending",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    out_dir = Path(settings.artifact_dir) / f"run_{run.id}"
    try:
        inp = GeneratorInput.model_validate(scenario.input_json)
        if inp.options.scenario_id is None:
            inp.options.scenario_id = scenario.slug
        outcome = run_generation(
            inp,
            out_dir,
            seed=seed,
            write_xlsx=write_xlsx,
        )
        pack = outcome.pack
        validation = outcome.validation.as_dict()
        run.artifact_dir = str(out_dir.resolve())
        run.validation_ok = outcome.ok if not outcome.test_only_broken else False
        run.validation_json = validation
        run.seed = outcome.seed_used
        if pack is not None:
            run.pack_summary = _pack_summary(pack)
        if outcome.test_only_broken:
            run.status = "ok"
            run.validation_ok = False
            run.error_message = "TEST_ONLY_BROKEN: validation failed as expected (VR-05)"
        elif outcome.ok and pack is not None:
            run.status = "ok"
        else:
            run.status = "error"
            run.error_message = outcome.error_message or "Generated pack failed validation"
    except Exception as exc:  # noqa: BLE001
        run.status = "error"
        run.error_message = str(exc)

    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def create_from_text_run(
    session: Session,
    settings: Settings,
    *,
    text: str,
    llm: str = "ollama",
    ollama_model: str | None = None,
    seed: int = 42,
) -> GenerationRun:
    """Create a running from-text row and seed progress.json (does not call Ollama)."""
    from payloq_api.services.progress import write_progress

    resolved_model = (
        (ollama_model or settings.ollama_model or DEFAULT_OLLAMA_MODEL)
        if llm == "ollama"
        else None
    )
    run = GenerationRun(
        source="from_text",
        llm_adapter=llm,
        llm_model=resolved_model,
        seed=seed,
        status="running",
        from_text=text,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    out_dir = Path(settings.artifact_dir) / f"run_{run.id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_progress(
        out_dir,
        percent=2,
        stage="queued",
        label_en="Queued — starting in background…",
        label_fi="Jonossa — käynnistyy taustalla…",
    )
    run.artifact_dir = str(out_dir.resolve())
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def execute_from_text(
    session: Session,
    settings: Settings,
    run: GenerationRun,
    *,
    text: str,
    llm: str = "ollama",
    language: str = "fi",
    industry: str = "unspecified",
    company_size: str = "small",
    months: int = 12,
    seed: int = 42,
    write_xlsx: bool = True,
    ollama_model: str | None = None,
    ollama_host: str | None = None,
    save_as_slug: str | None = None,
    compare: bool = True,
    compare_models: list[str] | None = None,
) -> GenerationRun:
    """Run Ollama extract → pack → validate → optional compare with progress updates."""
    from payloq_api.services.model_compare import (
        resolve_compare_models,
        run_model_comparison,
    )
    from payloq_api.services.progress import write_progress

    resolved_model = (
        (ollama_model or settings.ollama_model or DEFAULT_OLLAMA_MODEL)
        if llm == "ollama"
        else run.llm_model
    )
    out_dir = (
        Path(run.artifact_dir)
        if run.artifact_dir
        else Path(settings.artifact_dir) / f"run_{run.id}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    run.artifact_dir = str(out_dir.resolve())
    run.status = "running"
    session.add(run)
    session.commit()

    def _progress(
        percent: int,
        stage: str,
        label_en: str,
        label_fi: str | None = None,
        *,
        done: bool = False,
        error: str | None = None,
    ) -> None:
        write_progress(
            out_dir,
            percent=percent,
            stage=stage,
            label_en=label_en,
            label_fi=label_fi,
            done=done,
            error=error,
        )

    try:
        if llm != "ollama":
            raise ValueError(
                "From-text generation requires Ollama (local model)."
            )
        _progress(
            8,
            "extract",
            "Extracting parameters with Ollama…",
            "Poimitaan parametreja Ollamalla…",
        )
        host = ollama_host or settings.ollama_host or DEFAULT_OLLAMA_HOST
        adapter = get_adapter(
            "ollama",
            model=resolved_model or DEFAULT_OLLAMA_MODEL,
            host=host,
            timeout_s=settings.ollama_timeout,
        )
        opts = default_options_from_text(
            industry=industry,
            company_size=company_size,
            months=months,
            language=language,
            seed=seed,
        )
        inp = input_from_text(
            text=text,
            adapter=adapter,
            language=language,
            options=opts,
            with_invoice_texts=True,
        )
        llm_name = "ollama"
        run.llm_adapter = "ollama"
        if resolved_model:
            run.llm_model = resolved_model
        session.add(run)
        session.commit()

        _progress(
            40,
            "generate",
            "Building scenario pack (code)…",
            "Rakennetaan skenaariopakettia (koodi)…",
        )
        outcome = run_generation(
            inp,
            out_dir,
            seed=seed,
            write_xlsx=write_xlsx,
            raw_llm_output=getattr(adapter, "last_raw_output", None),
            llm_name=llm_name,
        )
        pack = outcome.pack
        _progress(
            50,
            "validate",
            "Validating pack…",
            "Validoidaan pakettia…",
        )
        soft = assess_nl_params(
            text,
            (pack.input.parameters_from_language_model.model_dump() if pack else {}),
            language=language,
        )
        run.artifact_dir = str(out_dir.resolve())
        run.validation_ok = outcome.ok
        run.validation_json = outcome.validation.as_dict()
        run.seed = outcome.seed_used
        if pack is not None:
            run.pack_summary = _pack_summary(pack, nl_soft_warnings=soft)
        if outcome.ok and pack is not None:
            run.status = "ok"
        else:
            run.status = "error"
            run.error_message = outcome.error_message or "Generated pack failed validation"
            _progress(
                100,
                "error",
                "Validation failed",
                "Validointi epäonnistui",
                done=True,
                error=run.error_message,
            )

        # PL-52: score shortlist on the same code-owned pack (best-effort; never fail the run).
        if (
            compare
            and outcome.ok
            and pack is not None
            and compare_models != []
        ):
            try:
                tags = resolve_compare_models(
                    requested=compare_models,
                    primary=resolved_model,
                    host=host,
                    available_only=True,
                )
                if tags:
                    run_model_comparison(
                        pack=pack,
                        text=text,
                        language=language,
                        options=opts,
                        models=tags,
                        pack_model=resolved_model,
                        host=host,
                        timeout_s=settings.ollama_timeout,
                        out_dir=out_dir,
                        on_progress=_progress,
                    )
            except Exception as cmp_exc:  # noqa: BLE001
                # Persist a soft note; pack artifacts remain the source of truth.
                note = f"model compare skipped: {cmp_exc}"
                run.llm_fallback_note = (
                    f"{run.llm_fallback_note}; {note}"
                    if run.llm_fallback_note
                    else note
                )

        if save_as_slug and outcome.ok and pack is not None:
            scenario = Scenario(
                slug=save_as_slug,
                title_fi=inp.scenario_description.fi[:120],
                title_en=inp.scenario_description.en[:120],
                description_fi=inp.scenario_description.fi,
                description_en=inp.scenario_description.en,
                is_preset=False,
                input_json=json.loads(inp.model_dump_json()),
            )
            session.add(scenario)
            session.commit()
            session.refresh(scenario)
            run.scenario_id = scenario.id

        if run.status == "ok":
            _progress(
                100,
                "done",
                "Complete",
                "Valmis",
                done=True,
            )
    except Exception as exc:  # noqa: BLE001
        run.status = "error"
        run.error_message = str(exc)
        _progress(
            100,
            "error",
            "Failed",
            "Epäonnistui",
            done=True,
            error=str(exc),
        )

    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def run_from_text(
    session: Session,
    settings: Settings,
    *,
    text: str,
    llm: str = "ollama",
    language: str = "fi",
    industry: str = "unspecified",
    company_size: str = "small",
    months: int = 12,
    seed: int = 42,
    write_xlsx: bool = True,
    ollama_model: str | None = None,
    ollama_host: str | None = None,
    save_as_slug: str | None = None,
    compare: bool = True,
    compare_models: list[str] | None = None,
) -> GenerationRun:
    """Synchronous from-text (tests / callers that need a finished run)."""
    run = create_from_text_run(
        session,
        settings,
        text=text,
        llm=llm,
        ollama_model=ollama_model,
        seed=seed,
    )
    return execute_from_text(
        session,
        settings,
        run,
        text=text,
        llm=llm,
        language=language,
        industry=industry,
        company_size=company_size,
        months=months,
        seed=seed,
        write_xlsx=write_xlsx,
        ollama_model=ollama_model,
        ollama_host=ollama_host,
        save_as_slug=save_as_slug,
        compare=compare,
        compare_models=compare_models,
    )


def execute_from_text_job(
    run_id: int,
    *,
    text: str,
    llm: str = "ollama",
    language: str = "fi",
    industry: str = "unspecified",
    company_size: str = "small",
    months: int = 12,
    seed: int = 42,
    write_xlsx: bool = True,
    ollama_model: str | None = None,
    ollama_host: str | None = None,
    save_as_slug: str | None = None,
    compare: bool = True,
    compare_models: list[str] | None = None,
) -> None:
    """Background worker: open a fresh DB session and finish the run."""
    from payloq_api.db import get_engine
    from payloq_api.config import get_settings

    settings = get_settings()
    with Session(get_engine()) as session:
        run = session.get(GenerationRun, run_id)
        if run is None:
            return
        execute_from_text(
            session,
            settings,
            run,
            text=text,
            llm=llm,
            language=language,
            industry=industry,
            company_size=company_size,
            months=months,
            seed=seed,
            write_xlsx=write_xlsx,
            ollama_model=ollama_model,
            ollama_host=ollama_host,
            save_as_slug=save_as_slug,
            compare=compare,
            compare_models=compare_models,
        )


def load_preset_input(settings: Settings, slug: str) -> GeneratorInput:
    path = settings.repo_root / "scenarios" / slug / "input.json"
    if not path.exists():
        raise FileNotFoundError(f"Unknown preset scenario: {slug}")
    return load_input(path)


def artifacts_for_run(run: GenerationRun) -> list[str]:
    if not run.artifact_dir:
        return []
    return _list_artifacts(Path(run.artifact_dir))

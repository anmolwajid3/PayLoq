"""Generate packs and fetch run artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from payloq_api.auth import get_current_user
from payloq_api.config import Settings, get_settings
from payloq_api.db import get_session
from payloq_api.models import GenerationRun, Scenario, User
from payloq_api.schemas import (
    ChatPresetOut,
    ChatRequest,
    ChatResponse,
    ChatSuggestionsRequest,
    GenerateFromTextRequest,
    GeneratePresetRequest,
    OllamaModelOut,
    OllamaModelsResponse,
    RunOut,
    RunProgressOut,
)
from payloq_api.services.chat import (
    chat_on_run,
    demo_presets_payload,
    resolve_run_chat_llm,
    result_to_dict,
    suggestions_for_run,
)
from payloq_api.services.generate import (
    artifacts_for_run,
    create_from_text_run,
    create_preset_run,
    execute_from_text_job,
    execute_preset_job,
    run_from_text,
    run_preset,
)
from payloq_api.services.model_compare import load_comparison
from payloq_api.services.progress import load_progress
from payloq_llm.adapters import list_ollama_models
from payloq_llm.defaults import DEFAULT_COMPARE_MODELS, UI_SUGGESTED_OLLAMA_TAGS

router = APIRouter(tags=["runs"])


def _run_out(run: GenerationRun) -> RunOut:
    raw = load_progress(run.artifact_dir)
    progress = RunProgressOut(**raw) if raw else None
    return RunOut(
        id=run.id or 0,
        scenario_id=run.scenario_id,
        source=run.source,
        llm_adapter=run.llm_adapter,
        llm_model=run.llm_model,
        llm_fallback_note=run.llm_fallback_note,
        seed=run.seed,
        status=run.status,
        error_message=run.error_message,
        artifact_dir=run.artifact_dir,
        validation_ok=run.validation_ok,
        validation_json=run.validation_json,
        pack_summary=run.pack_summary,
        from_text=run.from_text,
        created_at=run.created_at,
        artifacts=artifacts_for_run(run),
        comparison=load_comparison(run.artifact_dir),
        progress=progress,
    )


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = 50,
) -> list[RunOut]:
    rows = session.exec(
        select(GenerationRun).order_by(GenerationRun.id.desc()).limit(min(limit, 200))
    ).all()
    return [_run_out(r) for r in rows]


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(
    run_id: int,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> RunOut:
    run = session.get(GenerationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_out(run)


@router.post("/generate/preset", response_model=RunOut)
def generate_preset(
    body: GeneratePresetRequest,
    background_tasks: BackgroundTasks,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunOut:
    scenario = session.exec(select(Scenario).where(Scenario.slug == body.scenario_slug)).first()
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"Scenario '{body.scenario_slug}' not found")
    kwargs = dict(
        seed=body.seed,
        write_xlsx=body.write_xlsx,
        compare=body.compare,
        compare_models=body.compare_models,
        language=body.language,
    )
    if body.background:
        run = create_preset_run(
            session, settings, scenario=scenario, seed=body.seed
        )
        background_tasks.add_task(
            execute_preset_job,
            run.id,
            scenario.id,
            **kwargs,
        )
        return _run_out(run)
    run = run_preset(session, settings, scenario=scenario, **kwargs)
    return _run_out(run)


@router.post("/generate/from-text", response_model=RunOut)
def generate_from_text(
    body: GenerateFromTextRequest,
    background_tasks: BackgroundTasks,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunOut:
    kwargs = dict(
        text=body.text,
        llm=body.llm,
        language=body.language,
        industry=body.industry,
        company_size=body.company_size,
        months=body.months,
        seed=body.seed,
        write_xlsx=body.write_xlsx,
        ollama_model=body.ollama_model,
        ollama_host=body.ollama_host,
        save_as_slug=body.save_as_slug,
        compare=body.compare,
        compare_models=body.compare_models,
    )
    if body.background:
        run = create_from_text_run(
            session,
            settings,
            text=body.text,
            llm=body.llm,
            ollama_model=body.ollama_model,
            seed=body.seed,
        )
        background_tasks.add_task(execute_from_text_job, run.id, **kwargs)
        return _run_out(run)
    run = run_from_text(session, settings, **kwargs)
    return _run_out(run)


@router.get("/llm/models", response_model=OllamaModelsResponse)
def llm_models(
    _: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OllamaModelsResponse:
    """List local Ollama models (``/api/tags``). Web Generate uses this for Ollama tags."""
    payload = list_ollama_models(settings.ollama_host)
    return OllamaModelsResponse(
        available=bool(payload.get("available")),
        host=str(payload.get("host") or settings.ollama_host),
        models=[OllamaModelOut(**m) for m in (payload.get("models") or [])],
        error=payload.get("error"),
        recommended=list(UI_SUGGESTED_OLLAMA_TAGS),
        compare_shortlist=list(DEFAULT_COMPARE_MODELS),
    )


@router.get("/chat/presets", response_model=list[ChatPresetOut])
def chat_presets(
    _: Annotated[User, Depends(get_current_user)],
    language: Literal["fi", "en"] = "fi",
) -> list[ChatPresetOut]:
    return [ChatPresetOut(**row) for row in demo_presets_payload(language)]


@router.post("/runs/{run_id}/chat/suggestions", response_model=list[ChatPresetOut])
def chat_suggestions(
    run_id: int,
    body: ChatSuggestionsRequest,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[ChatPresetOut]:
    """Dynamic follow-ups from prior questions + this run's code figures."""
    run = session.get(GenerationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "ok" or not run.artifact_dir:
        raise HTTPException(status_code=400, detail="Run has no usable artifacts")
    try:
        rows = suggestions_for_run(
            run,
            language=body.language,
            prior_questions=body.prior_questions,
            limit=body.limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [ChatPresetOut(**row) for row in rows]


@router.post("/runs/{run_id}/chat", response_model=ChatResponse)
def chat_run(
    run_id: int,
    body: ChatRequest,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatResponse:
    run = session.get(GenerationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "ok" or not run.artifact_dir:
        raise HTTPException(status_code=400, detail="Run has no usable artifacts")
    if not body.question and not body.preset:
        raise HTTPException(status_code=400, detail="Provide question or preset")
    _, resolved_model = resolve_run_chat_llm(
        run,
        settings,
        llm_override=body.llm,
        ollama_model_override=body.ollama_model,
    )
    try:
        result = chat_on_run(
            run,
            settings,
            question=body.question,
            preset=body.preset,
            language=body.language,
            llm=body.llm,
            ollama_model=body.ollama_model,
            ollama_host=body.ollama_host,
            no_fallback_stub=body.no_fallback_stub,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc
    return ChatResponse(**result_to_dict(result, llm_model=resolved_model))



@router.get("/runs/{run_id}/artifacts/{filename}")
def download_artifact(
    run_id: int,
    filename: str,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    run = session.get(GenerationRun, run_id)
    if run is None or not run.artifact_dir:
        raise HTTPException(status_code=404, detail="Run or artifacts not found")
    # Prevent path traversal
    safe = Path(filename).name
    path = Path(run.artifact_dir) / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    media = "application/json"
    if safe.endswith(".xlsx"):
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(path, media_type=media, filename=safe)

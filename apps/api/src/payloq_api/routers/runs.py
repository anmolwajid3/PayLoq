"""Generate packs and fetch run artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from payloq_api.auth import get_current_user
from payloq_api.config import Settings, get_settings
from payloq_api.db import get_session
from payloq_api.models import GenerationRun, Scenario, User
from payloq_api.schemas import GenerateFromTextRequest, GeneratePresetRequest, RunOut
from payloq_api.services.generate import artifacts_for_run, run_from_text, run_preset

router = APIRouter(tags=["runs"])


def _run_out(run: GenerationRun) -> RunOut:
    return RunOut(
        id=run.id or 0,
        scenario_id=run.scenario_id,
        source=run.source,
        llm_adapter=run.llm_adapter,
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
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunOut:
    scenario = session.exec(select(Scenario).where(Scenario.slug == body.scenario_slug)).first()
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"Scenario '{body.scenario_slug}' not found")
    run = run_preset(
        session,
        settings,
        scenario=scenario,
        seed=body.seed,
        write_xlsx=body.write_xlsx,
    )
    return _run_out(run)


@router.post("/generate/from-text", response_model=RunOut)
def generate_from_text(
    body: GenerateFromTextRequest,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunOut:
    run = run_from_text(
        session,
        settings,
        text=body.text,
        llm=body.llm,
        language=body.language,
        industry=body.industry,
        months=body.months,
        seed=body.seed,
        write_xlsx=body.write_xlsx,
        ollama_model=body.ollama_model,
        ollama_host=body.ollama_host,
        no_fallback_stub=body.no_fallback_stub,
        save_as_slug=body.save_as_slug,
    )
    return _run_out(run)


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

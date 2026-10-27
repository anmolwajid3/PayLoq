"""Scenario browse / create."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from payloq_api.auth import get_current_user
from payloq_api.db import get_session
from payloq_api.models import Scenario, User
from payloq_api.schemas import ScenarioCreate, ScenarioOut
from payloq_schemas.models import GeneratorInput

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _out(s: Scenario) -> ScenarioOut:
    return ScenarioOut(
        id=s.id or 0,
        slug=s.slug,
        title_fi=s.title_fi,
        title_en=s.title_en,
        description_fi=s.description_fi,
        description_en=s.description_en,
        is_preset=s.is_preset,
        input_json=s.input_json,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.get("", response_model=list[ScenarioOut])
def list_scenarios(
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[ScenarioOut]:
    rows = session.exec(select(Scenario).order_by(Scenario.is_preset.desc(), Scenario.slug)).all()
    return [_out(r) for r in rows]


@router.get("/{slug}", response_model=ScenarioOut)
def get_scenario(
    slug: str,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ScenarioOut:
    row = session.exec(select(Scenario).where(Scenario.slug == slug)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return _out(row)


@router.post("", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED)
def create_scenario(
    body: ScenarioCreate,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ScenarioOut:
    existing = session.exec(select(Scenario).where(Scenario.slug == body.slug)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Slug already exists")
    try:
        GeneratorInput.model_validate(body.input_json)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Invalid input_json: {exc}") from exc

    now = datetime.now(timezone.utc)
    row = Scenario(
        slug=body.slug,
        title_fi=body.title_fi,
        title_en=body.title_en,
        description_fi=body.description_fi,
        description_en=body.description_en,
        is_preset=False,
        input_json=body.input_json,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _out(row)

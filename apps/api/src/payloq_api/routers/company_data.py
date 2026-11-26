"""Session-only company Excel/CSV upload + chat (PL-56)."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from payloq_api.auth import get_current_user
from payloq_api.config import Settings, get_settings
from payloq_api.models import User
from payloq_api.services import session_upload as su
from payloq_llm.adapters import get_adapter
from payloq_llm.defaults import (
    DEFAULT_COMPARE_MODELS,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
)

router = APIRouter(prefix="/company-data", tags=["company-data"])


class CompanySessionOut(BaseModel):
    username: str
    created_at: float
    expires_at: float
    ttl_remaining_s: int
    filenames: list[str]
    notes: list[str] = Field(default_factory=list)
    model: str | None = None
    has_figures: bool = False
    figure_summary: dict[str, Any] = Field(default_factory=dict)
    situation_report: str | None = None
    chat: list[dict[str, Any]] = Field(default_factory=list)


class CompanyChatRequest(BaseModel):
    question: str = Field(min_length=2)
    language: str = "fi"
    ollama_model: str | None = None


class CompanyChatResponse(BaseModel):
    answer: str
    model: str | None
    session: CompanySessionOut


def _figures_for_llm(sess: su.CompanySession) -> dict[str, Any]:
    figs = sess.figures or {}
    summary = figs.get("summary") or figs.get("peek") or figs
    # Cap size for prompt safety
    raw = json.dumps(summary, ensure_ascii=False, default=str)
    if len(raw) > 24_000:
        raw = raw[:24_000] + "…"
        return {"truncated_summary": raw, "filenames": sess.filenames}
    return summary if isinstance(summary, dict) else {"summary": summary}


@router.get("/session", response_model=CompanySessionOut)
def get_company_session(
    user: Annotated[User, Depends(get_current_user)],
) -> CompanySessionOut:
    sess = su.get_session(user.username)
    if sess is None:
        raise HTTPException(status_code=404, detail="No active company-data session")
    return CompanySessionOut(**su.session_public(sess))


@router.delete("/session")
def discard_company_session(
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    return {"cleared": su.clear_session(user.username)}


@router.post("/upload", response_model=CompanySessionOut)
async def upload_company_files(
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    files: list[UploadFile] = File(...),
) -> CompanySessionOut:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    blobs: list[tuple[str, bytes]] = []
    for f in files:
        name = f.filename or "upload.bin"
        data = await f.read()
        if len(data) > 8_000_000:
            raise HTTPException(status_code=400, detail=f"{name} too large (max 8MB)")
        blobs.append((name, data))
    try:
        ttl = float(settings.jwt_expire_hours) * 3600
        sess = su.upsert_uploads(user.username, blobs, ttl_s=ttl, replace=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CompanySessionOut(**su.session_public(sess))


@router.post("/situation-report", response_model=CompanyChatResponse)
def situation_report(
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    body: CompanyChatRequest | None = None,
) -> CompanyChatResponse:
    sess = su.get_session(user.username)
    if sess is None:
        raise HTTPException(status_code=404, detail="Upload company data first")
    language = (body.language if body else "fi") or "fi"
    model = (
        (body.ollama_model if body else None)
        or settings.ollama_model
        or DEFAULT_COMPARE_MODELS[-1]
        or DEFAULT_OLLAMA_MODEL
    )
    figures = _figures_for_llm(sess)
    if language == "fi":
        question = (
            "Kirjoita lyhyt virtuaalikirjanpitäjän tilanneraportti yhtiöstä. "
            "Käytä vain annettuja lukuja; älä keksi syitä. Mainitse kassa, "
            "avoimet laskut ja lähiviikkojen riskit jos luvut sen näyttävät."
        )
    else:
        question = (
            "Write a short virtual-accountant situation report for this company. "
            "Use only the given figures; do not invent causes. Mention cash, "
            "open invoices, and near-term risks when the figures show them."
        )
    try:
        adapter = get_adapter(
            "ollama",
            fallback_stub=False,
            model=model,
            host=settings.ollama_host or DEFAULT_OLLAMA_HOST,
            timeout_s=settings.ollama_timeout,
        )
        answer = adapter.interpret_figures(question, figures)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Report failed: {exc}") from exc

    su.append_chat(user.username, "user", question)
    su.append_chat(user.username, "assistant", answer)
    sess = su.set_report(user.username, answer, model=model)
    return CompanyChatResponse(
        answer=answer,
        model=model,
        session=CompanySessionOut(**su.session_public(sess)),
    )


@router.post("/chat", response_model=CompanyChatResponse)
def chat_company_data(
    body: CompanyChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CompanyChatResponse:
    sess = su.get_session(user.username)
    if sess is None:
        raise HTTPException(status_code=404, detail="Upload company data first")
    model = body.ollama_model or sess.model or settings.ollama_model or DEFAULT_OLLAMA_MODEL
    figures = _figures_for_llm(sess)
    try:
        adapter = get_adapter(
            "ollama",
            fallback_stub=False,
            model=model,
            host=settings.ollama_host or DEFAULT_OLLAMA_HOST,
            timeout_s=settings.ollama_timeout,
        )
        answer = adapter.interpret_figures(body.question, figures)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Chat failed: {exc}") from exc

    su.append_chat(user.username, "user", body.question)
    sess = su.append_chat(user.username, "assistant", answer)
    sess.model = model
    return CompanyChatResponse(
        answer=answer,
        model=model,
        session=CompanySessionOut(**su.session_public(sess)),
    )

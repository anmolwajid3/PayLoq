"""API request / response DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    display_name: str


class UserOut(BaseModel):
    username: str
    display_name: str


class ScenarioCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    title_fi: str
    title_en: str
    description_fi: str
    description_en: str
    input_json: dict[str, Any]


class ScenarioOut(BaseModel):
    id: int
    slug: str
    title_fi: str
    title_en: str
    description_fi: str
    description_en: str
    is_preset: bool
    input_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class GeneratePresetRequest(BaseModel):
    scenario_slug: str
    seed: int = 42
    write_xlsx: bool = True
    write_journal: bool = True


class GenerateFromTextRequest(BaseModel):
    text: str = Field(min_length=3)
    llm: Literal["stub", "ollama"] = "stub"
    language: Literal["fi", "en"] = "fi"
    industry: str = "metal workshop (machine shop)"
    months: int = Field(default=12, ge=12, le=24)
    seed: int = 42
    write_xlsx: bool = True
    write_journal: bool = True
    ollama_model: Optional[str] = None
    ollama_host: Optional[str] = None
    no_fallback_stub: bool = False
    save_as_slug: Optional[str] = Field(
        default=None,
        description="If set, also persist a Scenario row from the generated input.",
    )


class ChatRequest(BaseModel):
    question: Optional[str] = Field(
        default=None,
        description="Free-form FI/EN question. Overrides preset when set.",
    )
    preset: Optional[Literal["cash_drop", "cash_negative"]] = None
    language: Literal["fi", "en"] = "fi"
    llm: Literal["stub", "ollama"] = "stub"
    ollama_model: Optional[str] = None
    ollama_host: Optional[str] = None
    no_fallback_stub: bool = False


class ChatResponse(BaseModel):
    question: str
    answer: str
    figures: dict[str, Any]
    preset: Optional[str] = None
    llm_adapter: str
    fallback_note: Optional[str] = None
    metrics: Optional[dict[str, Any]] = None


class ChatPresetOut(BaseModel):
    id: str
    question: str


class ValidationIssueOut(BaseModel):
    code: str
    message: str
    severity: str


class RunOut(BaseModel):
    id: int
    scenario_id: Optional[int]
    source: str
    llm_adapter: str
    llm_fallback_note: Optional[str]
    seed: int
    status: str
    error_message: Optional[str]
    artifact_dir: Optional[str]
    validation_ok: Optional[bool]
    validation_json: Optional[dict[str, Any]]
    pack_summary: Optional[dict[str, Any]]
    from_text: Optional[str]
    created_at: datetime
    artifacts: list[str] = Field(default_factory=list)


class HealthOut(BaseModel):
    status: str
    database: str
    artifact_dir: str

"""API request / response DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from payloq_schemas.company_size import parse_company_size


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
    language: Literal["fi", "en"] = "fi"
    compare: bool = Field(
        default=False,
        description="Score compare_models on the same preset pack (PL-55). UI should set true.",
    )
    compare_models: Optional[list[str]] = Field(
        default=None,
        description="Ollama tags to compare. Null = size-ladder shortlist. Empty skips.",
    )
    background: bool = Field(
        default=False,
        description=(
            "When true, return running immediately and finish pack/compare in background. "
            "UI should set true; tests keep false."
        ),
    )


class GenerateFromTextRequest(BaseModel):
    text: str = Field(min_length=3)
    llm: Literal["ollama"] = "ollama"
    language: Literal["fi", "en"] = "fi"
    industry: str = "unspecified"
    company_size: str = Field(
        ...,
        description=(
            "Employee count (e.g. 8, 420, or '12 employees') or label "
            "small/medium/large (case-insensitive; FI: pieni/keskikokoinen/suuri)."
        ),
    )
    months: int = Field(default=12, ge=12, le=24)
    seed: int = 42
    write_xlsx: bool = True
    ollama_model: Optional[str] = None
    ollama_host: Optional[str] = None
    save_as_slug: Optional[str] = Field(
        default=None,
        description="If set, also persist a Scenario row from the generated input.",
    )
    # PL-52: multi-model compare on every NL generate (default shortlist when null).
    compare: bool = Field(
        default=True,
        description="When true, score compare_models on the same pack and attach comparison.",
    )
    compare_models: Optional[list[str]] = Field(
        default=None,
        description=(
            "Ollama tags to compare. Null = size ladder "
            "(llama3.2:1b, 3b, qwen2.5:3b, qwen2.5:7b) + finance when pulled, plus primary. "
            "Empty list skips."
        ),
    )
    background: bool = Field(
        default=True,
        description=(
            "When true (default), return a running run immediately and finish "
            "Ollama extract / pack / compare in a background task. Poll GET /runs/{id}."
        ),
    )

    @field_validator("company_size")
    @classmethod
    def _normalize_company_size(cls, value: str) -> str:
        return parse_company_size(value)

    @field_validator("months")
    @classmethod
    def _months_range_message(cls, value: int) -> int:
        # Pydantic ge/le already enforces; keep SRS wording for explicit checks.
        if value < 12 or value > 24:
            raise ValueError("Months must be between 12 and 24.")
        return value


class ChatRequest(BaseModel):
    question: Optional[str] = Field(
        default=None,
        description="Free-form FI/EN question. Overrides preset when set.",
    )
    preset: Optional[Literal["cash_drop", "cash_negative"]] = None
    language: Literal["fi", "en"] = "fi"
    # Optional override for tests/CLI. UI omits this — chat uses the run's stored model.
    llm: Optional[Literal["stub", "ollama"]] = None
    ollama_model: Optional[str] = None
    ollama_host: Optional[str] = None
    no_fallback_stub: bool = False


class ChatResponse(BaseModel):
    question: str
    answer: str
    figures: dict[str, Any]
    preset: Optional[str] = None
    llm_adapter: str
    llm_model: Optional[str] = None
    fallback_note: Optional[str] = None
    metrics: Optional[dict[str, Any]] = None


class ChatPresetOut(BaseModel):
    id: str
    question: str


class ChatSuggestionsRequest(BaseModel):
    language: Literal["fi", "en"] = "fi"
    prior_questions: list[str] = Field(default_factory=list)
    limit: int = Field(default=4, ge=1, le=8)


class OllamaModelOut(BaseModel):
    name: str
    size: Optional[int] = None
    modified_at: Optional[str] = None
    digest: Optional[str] = None
    parameter_size: Optional[str] = None
    family: Optional[str] = None


class OllamaModelsResponse(BaseModel):
    available: bool
    host: str
    models: list[OllamaModelOut] = Field(default_factory=list)
    error: Optional[str] = None
    recommended: list[str] = Field(
        default_factory=list,
        description="Suggested CPU-friendly tags to pull if missing.",
    )
    compare_shortlist: list[str] = Field(
        default_factory=list,
        description="Default PL-52 Generate compare tags (Mac Task B winners).",
    )


class ValidationIssueOut(BaseModel):
    code: str
    message: str
    severity: str


class RunProgressOut(BaseModel):
    percent: int = 0
    stage: str = ""
    label_en: str = ""
    label_fi: str = ""
    done: bool = False
    error: Optional[str] = None


class RunOut(BaseModel):
    id: int
    scenario_id: Optional[int]
    source: str
    llm_adapter: str
    llm_model: Optional[str] = None
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
    comparison: Optional[dict[str, Any]] = Field(
        default=None,
        description="PL-52 multi-model compare payload (from comparison.json when present).",
    )
    progress: Optional[RunProgressOut] = Field(
        default=None,
        description="Live percent/stage from progress.json while status is running.",
    )


class HealthOut(BaseModel):
    status: str
    database: str
    artifact_dir: str

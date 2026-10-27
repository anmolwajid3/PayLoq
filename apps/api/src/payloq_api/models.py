"""Persistent ORM models for the PayLoq app layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, JSON, Text
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, max_length=64)
    password_hash: str
    display_name: str = "PayLoq"
    created_at: datetime = Field(default_factory=_utcnow)


class Scenario(SQLModel, table=True):
    """Browsable scenario (preset or user-created)."""

    __tablename__ = "scenarios"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True, max_length=64)
    title_fi: str
    title_en: str
    description_fi: str = Field(sa_column=Column(Text))
    description_en: str = Field(sa_column=Column(Text))
    is_preset: bool = False
    # Full GeneratorInput JSON (params + options + description)
    input_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class GenerationRun(SQLModel, table=True):
    """One generate invocation (preset or NL)."""

    __tablename__ = "generation_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    scenario_id: Optional[int] = Field(default=None, foreign_key="scenarios.id", index=True)
    source: str = Field(max_length=32)  # preset | from_text | custom_input
    llm_adapter: str = Field(default="none", max_length=32)  # none | stub | ollama
    llm_fallback_note: Optional[str] = Field(default=None, sa_column=Column(Text))
    seed: int = 42
    status: str = Field(default="pending", max_length=32)  # pending | ok | error
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    artifact_dir: Optional[str] = None
    validation_ok: Optional[bool] = None
    validation_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    pack_summary: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    from_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=_utcnow)

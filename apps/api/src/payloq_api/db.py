"""SQLAlchemy / SQLModel engine and session helpers."""

from __future__ import annotations

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from payloq_api.config import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {}
        if settings.is_sqlite:
            connect_args["check_same_thread"] = False
            # Ensure parent dir exists for file SQLite
            url = settings.database_url
            if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
                from pathlib import Path

                db_path = Path(url.removeprefix("sqlite:///"))
                if not db_path.is_absolute():
                    db_path = Path.cwd() / db_path
                db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            settings.database_url,
            echo=False,
            connect_args=connect_args,
        )
    return _engine


def init_db() -> None:
    """Create tables (dev / SQLite). Prefer Alembic in production Postgres."""
    # Import models so metadata is populated
    import payloq_api.models  # noqa: F401
    from sqlalchemy import inspect, text

    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    # Lightweight ensure for columns added after first create_all (SQLite / local PoC).
    insp = inspect(engine)
    if "generation_runs" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("generation_runs")}
        if "llm_model" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE generation_runs ADD COLUMN llm_model VARCHAR(128)"))


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session

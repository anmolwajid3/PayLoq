"""Application settings (env-driven)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [Path.cwd(), *here.parents]:
        if (candidate / "scenarios").is_dir() and (candidate / "pyproject.toml").exists():
            return candidate
    return here.parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAYLOQ_", env_file=".env", extra="ignore")

    # sqlite:///./data/payloq.db  |  postgresql+psycopg://payloq:payloq@localhost:5432/payloq
    database_url: str = "sqlite:///./data/payloq.db"
    artifact_dir: Path = Path("./data/artifacts")
    repo_root: Path = _default_repo_root()

    # Single-user PoC auth
    auth_username: str = "payloq"
    auth_password: str = "payloq"
    jwt_secret: str = "payloq-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 72

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"

    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:1b"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()

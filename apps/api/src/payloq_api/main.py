"""FastAPI entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from payloq_api.config import Settings, get_settings
from payloq_api.db import init_db
from payloq_api.routers import auth, runs, scenarios
from payloq_api.schemas import HealthOut
from payloq_api.seed import seed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    seed()
    yield


app = FastAPI(
    title="PayLoq API",
    description=(
        "Research PoC — browse scenarios, generate packs, chat demo over figures, "
        "optional journal entries."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(scenarios.router, prefix="/api")
app.include_router(runs.router, prefix="/api")


@app.get("/api/health", response_model=HealthOut)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthOut:
    db_kind = "sqlite" if settings.is_sqlite else "postgres"
    return HealthOut(
        status="ok",
        database=db_kind,
        artifact_dir=str(settings.artifact_dir),
    )


def run() -> None:
    import uvicorn

    uvicorn.run(
        "payloq_api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    run()

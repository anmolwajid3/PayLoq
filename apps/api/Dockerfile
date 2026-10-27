FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/* \
  && curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

COPY pyproject.toml uv.lock README.md ./
COPY packages ./packages
COPY apps/cli ./apps/cli
COPY apps/api ./apps/api
COPY scenarios ./scenarios

RUN uv sync --package payloq-api --no-dev

ENV PAYLOQ_ARTIFACT_DIR=/data/artifacts
ENV PAYLOQ_REPO_ROOT=/app
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "payloq_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

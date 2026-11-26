# Ollama on Mac (Docker Compose)

Primary path: `~/Desktop/PayLoq`. The web **Generate** page lists whatever models Ollama reports via `/api/tags` — there is **no Stub** option in the UI.

**Timeouts:** NL→params on Docker Desktop CPU is slow. The API defaults to **300s** (`PAYLOQ_OLLAMA_TIMEOUT`); `docker-compose.yml` sets **600s** for the `api` service. If Generate still falls back to stub with a “timed out” note, raise it further (e.g. `900`) and recreate `api`.

## Start stack + pull small CPU models

```bash
cd ~/Desktop/PayLoq
git fetch --prune && git checkout main && git pull origin main
docker compose --profile ollama up --build -d
```

Wait until Ollama answers (not just “container up”):

```bash
until curl -sf http://127.0.0.1:11434/api/tags >/dev/null; do echo "waiting for ollama…"; sleep 2; done
echo "ollama ready"
```

Pull models into the Compose Ollama service:

```bash
docker compose --profile ollama exec ollama ollama pull llama3.2:1b
docker compose --profile ollama exec ollama ollama pull qwen2.5:0.5b
# Task B / size ladder (+ finance-tuned):
docker compose --profile ollama exec ollama ollama pull llama3.2:3b
docker compose --profile ollama exec ollama ollama pull qwen2.5:3b
docker compose --profile ollama exec ollama ollama pull qwen2.5:7b
docker compose --profile ollama exec ollama ollama pull FableForge-AI/nexus-finance:q4_k_m
docker compose --profile ollama exec ollama ollama list
```

Task B seeded scorecard (after pulls):

```bash
PAYLOQ_OLLAMA_TIMEOUT=600 uv run payloq bench \
  --config benchmarks/matrix.cpu.json \
  --out runs/benchmark_task_b_mac \
  --seed 42 --judge --spotcheck
```

Confirm the timeout env on `api` (expect `600`):

```bash
docker compose --profile ollama exec api printenv PAYLOQ_OLLAMA_TIMEOUT
```

Warm the model once (first load is the slow part on CPU):

```bash
curl -s http://127.0.0.1:11434/api/generate -d '{"model":"llama3.2:1b","prompt":"Say hi in one word.","stream":false}' | head -c 400
echo
```

Open http://localhost:5173 · `payloq` / `payloq`.

## Live (non-stub) Generate check

1. **Generate** → pick **`llama3.2:1b`** (not a missing tag).
2. Use a short FI description, e.g. *Pieni konepaja, kassa on kriittinen kolmen viikon päästä.*
3. Submit and wait — on Mac CPU this can take several minutes (budget up to the configured timeout).
4. On the run detail / runs list, LLM must show **`ollama`** (or `ollama · llama3.2:1b`), **not** `ollama->stub`.
5. If you see `ollama->stub`, open the fallback note: a timeout means raise `PAYLOQ_OLLAMA_TIMEOUT` and recreate api; “unavailable” means Ollama/host/model wiring.

Override timeout without editing the file:

```bash
PAYLOQ_OLLAMA_TIMEOUT=900 docker compose --profile ollama up -d --force-recreate api
docker compose --profile ollama exec api printenv PAYLOQ_OLLAMA_TIMEOUT
```

## Checkout a PR with `gh`

```bash
cd ~/Desktop/PayLoq
gh pr checkout <PR_NUMBER>
docker compose --profile ollama up --build -d
```

## Rebuild web image (UI-only changes)

Static Vite assets are baked into the `web` image. After pulling a UI PR, rebuild web without cache so nginx serves the new bundle:

```bash
cd ~/Desktop/PayLoq
gh pr checkout <PR_NUMBER>
docker compose --profile ollama build --no-cache web
docker compose --profile ollama up -d --force-recreate web
```

## After merge — sync main

```bash
cd ~/Desktop/PayLoq
git fetch --prune
git checkout main
git pull origin main
git branch -d cursor/<merged-branch>   # optional
```

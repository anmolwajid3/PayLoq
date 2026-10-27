# PayLoq

Research PoC for **synthetic Finnish SME financial datasets** (Task A) and a **local LLM “virtual accountant” benchmark** (Task B).

**Principle:** *Code calculates; the language model interprets.* All figures and consistency checks are ordinary Python. LLMs only map descriptions → parameters, write descriptive texts, and interpret ready-made figures.

Everything is **synthetic / fictional**. MIT licensed. Designed for **CPU-friendly local** runs (Ollama optional; stub fallback when Ollama is unavailable).

## App UI (API + web + DB)

Full-stack experimental UI: browse/create scenarios, generate packs (preset or NL), view JSON/Excel, validation, and cash charts.

**Login:** `payloq` / `payloq` · **UI:** http://localhost:5173 · **API docs:** http://localhost:8000/docs

### Windows — Docker Compose (recommended)

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) if needed, then (Command Prompt / `cmd`):

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & git pull origin main & docker compose up --build -d
```

Open http://localhost:5173 and sign in as `payloq` / `payloq`.

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & docker compose down
```

Step-by-step (SQLite fallback, Alembic): **[docs/app-windows.md](docs/app-windows.md)**.

### Windows — SQLite without Docker DB

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & uv sync & cd /d C:\Users\anmol\Desktop\PayLoq\apps\web & npm install
```

Terminal 1 (API):

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & set PAYLOQ_DATABASE_URL=sqlite:///./data/payloq.db & set PAYLOQ_ARTIFACT_DIR=./data/artifacts & uv run uvicorn payloq_api.main:app --host 127.0.0.1 --port 8000
```

Terminal 2 (web):

```bat
cd /d C:\Users\anmol\Desktop\PayLoq\apps\web & npm run dev
```

Open http://localhost:5173.

## CLI quick start (local, CPU)

Requires **Python 3.12+** and [uv](https://docs.astral.sh/uv/).

### Windows (Anmol’s Desktop path)

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & uv sync & uv run payloq generate --scenario cash_critical --out out\cash_critical & uv run payloq validate out\cash_critical
```

### Any platform

```bash
git clone https://github.com/anmolwajid3/PayLoq.git
cd PayLoq
uv sync
```

Generate the three built-in scenarios (**no LLM**):

```bash
uv run payloq generate --scenario good --out out/good
uv run payloq generate --scenario weak --out out/weak
uv run payloq generate --scenario cash_critical --out out/cash_critical
```

Validate a pack:

```bash
uv run payloq validate out/cash_critical
```

### Phase 2: generate from natural language

Stub adapter (always works, CPU-only keyword heuristics + FI/EN invoice texts):

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & uv run payloq generate --from-text "Pieni konepaja, kassa on kriittinen kolmen viikon päästä." --llm stub --out out\from_text_stub
```

```bash
uv run payloq generate --from-text "Pieni konepaja, kassa on kriittinen kolmen viikon päästä." --llm stub --out out/from_text_stub
```

Ollama (default small model `llama3.2:1b`; falls back to stub if Ollama is down):

```bat
ollama pull llama3.2:1b & cd /d C:\Users\anmol\Desktop\PayLoq & uv run payloq generate --from-text "Pieni konepaja, kassa on kriittinen kolmen viikon päästä." --llm ollama --out out\from_text_ollama
```

Full Windows Ollama install + commands: **[docs/ollama-windows.md](docs/ollama-windows.md)**.

### Benchmark + Ollama scorecard

CPU shortlist: **stub** (always) · **llama3.2:1b** (recommended) · optional **llama3.2:3b** / **qwen2.5:3b**. Live Ollama cells are **skipped** when the daemon is down (`--skip-unavailable`, default on).

Stub only — Windows:

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & uv sync & uv run payloq bench --models stub --out runs\benchmark
```

Recommended + optional matrix — Windows:

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & ollama pull llama3.2:1b & ollama pull llama3.2:3b & ollama pull qwen2.5:3b & uv run payloq bench --config benchmarks\matrix.cpu.json --out runs\benchmark_cpu
```

Any platform:

```bash
uv run payloq bench --models stub --out runs/benchmark
uv run payloq bench --models shortlist:recommended --out runs/benchmark_rec
uv run payloq bench --config benchmarks/matrix.cpu.json --out runs/benchmark_cpu
```

Writes `results.json`, `scorecard.json`, `scorecard.csv`, `runs.csv`, `metrics.sqlite`, and `spotcheck.csv` under `--out`. FI quality is a **separate band** (EN-only models are not failed on the main interpretation score). Details: [docs/evaluation.md](docs/evaluation.md).

## CLI

| Command | Purpose |
| --- | --- |
| `payloq generate -s <id> -o <dir>` | Preset params → JSON + Excel (no LLM) |
| `payloq generate -i input.json -o <dir>` | Same from a custom input file |
| `payloq generate --from-text "…" --llm stub\|ollama` | NL → params (+ invoice texts) → pack |
| `payloq generate --from-text-file desc.txt --llm ollama` | Same from a UTF-8 file |
| `payloq validate <dir>` | Balance / continuity / invoice checks |
| `payloq bench` | Model matrix + graders + scorecard (JSON/CSV/SQLite) |
| `payloq list-scenarios` | List `scenarios/*/input.json` |

Useful `--from-text` flags: `--ollama-model`, `--ollama-host`, `--no-fallback-stub`, `--language fi`, `--industry`, `--months`.

Useful `bench` flags: `--models` (`stub` / `shortlist` / `ollama:<tag>`), `--scenarios`, `--config`, `--judge`, `--spotcheck/--no-spotcheck`, `--skip-unavailable/--no-skip-unavailable`, `--ollama-host`, `--seed`.

## Built-in scenarios

| Id | Behaviour |
| --- | --- |
| `good` | Healthy cash, steady growth, solvent projection |
| `weak` | Falling revenue, losses, shrinking cash |
| `cash_critical` | Positive P&L; open-invoice projection goes **negative ~week 3** |

Fidelity target: **behavioural match** (not numeric golden match to the illustrative example zip).

## Add a scenario

1. Copy `scenarios/good/input.json` to `scenarios/<name>/input.json`
2. Edit FI + EN `scenario_description`, `options.scenario_id`, and parameters
3. `uv run payloq generate --scenario <name> --out out/<name>`
4. `uv run payloq validate out/<name>`

Or invent one from free text:

```bash
uv run payloq generate --from-text "…" --llm stub --out out/custom
```

See [docs/schema.md](docs/schema.md).

## Layout

```
packages/schemas|generator|validate|export_xlsx|llm|benchmark
apps/cli
apps/api          # FastAPI + SQLModel + Alembic (Postgres or SQLite)
apps/web          # Vite + React UI (FI/EN)
scenarios/{good,weak,cash_critical}
docker-compose.yml
docs/
tests/
```

## Phase status

- **Phase 0/1:** schemas, deterministic generator, validators, Excel export, CLI, LLM stubs
- **Phase 2:** NL → parameters via Ollama/stub; LLM invoice descriptive texts; CLI `--from-text` / `--llm`
- **Phase 3:** model matrix runner, parameter/reading/MoM/interpretation graders, SQLite metrics, optional judge + spot-check sheet
- **PL-7 scorecard:** CPU model shortlist, skip live if no Ollama, JSON/CSV/SQLite export, separate FI quality band
- **App layer:** FastAPI + DB + Vite UI for local experimentation
- **§4 nice-to-haves:** deferred (chat demo, journal entries, …)

## License

MIT — see [LICENSE](LICENSE).

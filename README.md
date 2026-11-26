# PayLoq

Synthetic Finnish SME financial scenarios for local experimentation.

**Rule:** code calculates the figures; the language model only extracts parameters and interprets those figures. Everything is fictional. MIT licensed.

## Quick start (Mac)

Checkout lives at `~/Desktop/PayLoq`.

```bash
cd ~/Desktop/PayLoq
git checkout main
git pull
docker compose --profile ollama up --build -d
```

Then open http://localhost:5173 and sign in with `payloq` / `payloq`.

API docs: http://localhost:8000/docs

Pull models into Compose Ollama so they appear under Generate:

```bash
cd ~/Desktop/PayLoq
docker compose --profile ollama exec ollama ollama pull qwen2.5:7b
docker compose --profile ollama exec ollama ollama pull llama3.2:3b
docker compose --profile ollama exec ollama ollama pull qwen2.5:3b
docker compose --profile ollama exec ollama ollama pull llama3.2:1b
docker compose --profile ollama exec ollama ollama list
```

## What you can do

- **Generate** a pack from a preset or from natural-language text (Ollama models only in the UI)
- **Compare** several local models on the same code-built figures
- **Browse** runs and scenarios, export PDF / Excel
- **Chat** about a run using the same model that built it
- **Company data** upload (session-only) for situation reports

## CLI (optional)

Needs Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cd ~/Desktop/PayLoq
uv sync
uv run payloq generate --scenario cash_critical --out out/cash_critical
uv run payloq validate out/cash_critical
uv run payloq list-scenarios
```

Built-in scenarios: `good`, `weak`, `cash_critical`.

## Docs

| Doc | Topic |
| --- | --- |
| [docs/ollama-mac.md](docs/ollama-mac.md) | Mac Ollama / Compose |
| [docs/evaluation.md](docs/evaluation.md) | Benchmark / scorecard |
| [docs/schema.md](docs/schema.md) | Pack schema |
| [docs/app-windows.md](docs/app-windows.md) | Windows / Docker Desktop |
| [docs/ollama-windows.md](docs/ollama-windows.md) | Windows Ollama |

## Layout

```
apps/api          FastAPI + DB
apps/web          Vite + React UI (FI/EN)
apps/cli          `payloq` CLI
packages/         schemas, generator, validate, llm, benchmark, export
scenarios/        built-in presets
tests/
docker-compose.yml
```

## License

MIT — see [LICENSE](LICENSE).

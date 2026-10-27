# PayLoq

Research PoC for **synthetic Finnish SME financial datasets** (Task A) and a **local LLM “virtual accountant” benchmark** (Task B).

**Principle:** *Code calculates; the language model interprets.* All figures and consistency checks are ordinary Python. LLMs only map descriptions → parameters, write descriptive texts, and interpret ready-made figures.

Everything is **synthetic / fictional**. MIT licensed. Designed for **CPU-friendly local** runs (Ollama optional; stub fallback when Ollama is unavailable).

## Quick start (local, CPU)

Requires **Python 3.12+** and [uv](https://docs.astral.sh/uv/).

### Windows (Anmol’s Desktop path)

```powershell
cd C:\Users\anmol\Desktop\PayLoq
uv sync
uv run payloq generate --scenario cash_critical --out out\cash_critical
uv run payloq validate out\cash_critical
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

```powershell
cd C:\Users\anmol\Desktop\PayLoq
uv run payloq generate --from-text "Pieni konepaja, kassa on kriittinen kolmen viikon päästä." --llm stub --out out\from_text_stub
```

```bash
uv run payloq generate --from-text "Pieni konepaja, kassa on kriittinen kolmen viikon päästä." --llm stub --out out/from_text_stub
```

Ollama (default small model `llama3.2:1b`; falls back to stub if Ollama is down):

```powershell
ollama pull llama3.2:1b
cd C:\Users\anmol\Desktop\PayLoq
uv run payloq generate --from-text "Pieni konepaja, kassa on kriittinen kolmen viikon päästä." --llm ollama --out out\from_text_ollama
```

Full Windows Ollama install + commands: **[docs/ollama-windows.md](docs/ollama-windows.md)**.

### Phase 3: benchmark harness

Stub matrix (CPU, no model download) — Windows (blank line between commands):

```powershell
cd C:\Users\anmol\Desktop\PayLoq

uv sync

uv run payloq bench --models stub --out runs\benchmark
```

Any platform:

```bash
uv run payloq bench --models stub --out runs/benchmark
uv run payloq bench --models stub,ollama:llama3.2:1b --out runs/benchmark_matrix
uv run payloq bench --config benchmarks/matrix.example.json --out runs/benchmark_cfg
```

Writes `results.json`, `scorecard.json`, `metrics.sqlite`, and a human `spotcheck.csv` under `--out`. Details: [docs/evaluation.md](docs/evaluation.md).

## CLI

| Command | Purpose |
| --- | --- |
| `payloq generate -s <id> -o <dir>` | Preset params → JSON + Excel (no LLM) |
| `payloq generate -i input.json -o <dir>` | Same from a custom input file |
| `payloq generate --from-text "…" --llm stub\|ollama` | NL → params (+ invoice texts) → pack |
| `payloq generate --from-text-file desc.txt --llm ollama` | Same from a UTF-8 file |
| `payloq validate <dir>` | Balance / continuity / invoice checks |
| `payloq bench` | Phase 3 model matrix + graders + SQLite metrics |
| `payloq list-scenarios` | List `scenarios/*/input.json` |

Useful `--from-text` flags: `--ollama-model`, `--ollama-host`, `--no-fallback-stub`, `--language fi`, `--industry`, `--months`.

Useful `bench` flags: `--models`, `--scenarios`, `--config`, `--judge`, `--spotcheck/--no-spotcheck`, `--ollama-host`, `--seed`.

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
scenarios/{good,weak,cash_critical}
docs/
tests/
```

## Phase status

- **Phase 0/1:** schemas, deterministic generator, validators, Excel export, CLI, LLM stubs
- **Phase 2:** NL → parameters via Ollama/stub; LLM invoice descriptive texts; CLI `--from-text` / `--llm`
- **Phase 3 (this):** model matrix runner, parameter/reading/MoM/interpretation graders, SQLite metrics, optional judge + spot-check sheet
- **§4 nice-to-haves:** deferred (chat demo, journal entries, …)

## License

MIT — see [LICENSE](LICENSE).

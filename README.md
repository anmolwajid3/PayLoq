# PayLoq

Research PoC for **synthetic Finnish SME financial datasets** (Task A) and a **local LLM “virtual accountant” benchmark** (Task B).

**Principle:** *Code calculates; the language model interprets.* All figures and consistency checks are ordinary Python. LLMs only map descriptions → parameters, write descriptive texts, and interpret ready-made figures.

Everything is **synthetic / fictional**. MIT licensed. Designed for **CPU-friendly local** runs (Ollama optional; no GPU required for generation).

## Quick start (local, CPU)

Requires **Python 3.12+** and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/anmolwajid3/PayLoq.git
cd PayLoq
uv sync
```

Generate the three built-in scenarios:

```bash
uv run payloq generate --scenario good --out out/good
uv run payloq generate --scenario weak --out out/weak
uv run payloq generate --scenario cash_critical --out out/cash_critical
```

Validate a pack:

```bash
uv run payloq validate out/cash_critical
```

Benchmark scaffold (stub adapter — no model download):

```bash
uv run payloq bench --models stub --out runs/benchmark
```

### Optional: Ollama

Generation does **not** need Ollama. For Phase 2/3 experiments:

```bash
# install Ollama separately, then e.g.:
# ollama pull llama3.2
```

The `payloq_llm.OllamaAdapter` talks to `http://127.0.0.1:11434` when you opt in later.

## CLI

| Command | Purpose |
| --- | --- |
| `payloq generate -s <id> -o <dir>` | Params → JSON + Excel pack |
| `payloq generate -i input.json -o <dir>` | Same from a custom input file |
| `payloq validate <dir>` | Balance / continuity / invoice checks |
| `payloq bench` | Phase 3 harness scaffold |
| `payloq list-scenarios` | List `scenarios/*/input.json` |

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

- **Phase 0/1 (this repo):** schemas, deterministic generator, validators, Excel export, CLI, LLM stubs, benchmark scaffold
- **Phase 2:** NL → parameters via real local models; richer descriptive text
- **Phase 3:** multi-model scorecard (latency, tokens, graders)
- **§4 nice-to-haves:** deferred (chat demo, journal entries, …)

## License

MIT — see [LICENSE](LICENSE).

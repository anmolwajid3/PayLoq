# Evaluation (Phase 3 benchmark)

Work order §3 metrics are implemented in `packages/benchmark` and driven by `payloq bench`.

## What is scored

| Metric | How |
| --- | --- |
| Parameter correctness | Code grader vs scenario `parameters_from_language_model` answer key (relative error + cost shares + `partly_fixed_costs`) |
| Figure reading | Code-checked numeric probes (`cash_end`, `revenue_last`, first negative projection week) |
| MoM change | Probe on `mom_revenue_change` from monthly reports |
| Interpretation quality | Rubric: factual (cites pack figures), understandable, no invented causes; optional LLM judge; human spot-check CSV |
| Latency / tokens / hardware | Per-call adapter metrics + `hardware.json` |
| Rough cost | Local energy proxy from tokens + wall time (`rough_cost_eur`) — not cloud API pricing |

**Principle:** packs used for reading/interpretation are generated from the **answer-key parameters** (code calculates). Models are graded on extraction from NL and on reading/interpreting ready-made figures.

## Artifacts under `runs/benchmark/` (gitignored)

| File | Purpose |
| --- | --- |
| `results.json` | Full run log + per-field grade detail |
| `scorecard.json` | Aggregates by model |
| `metrics.sqlite` | SQLite store (`benchmark_runs` table) |
| `hardware.json` | Platform fingerprint |
| `pack_summary_<scenario>.json` | Figures shown to models |
| `spotcheck.csv` + `spotcheck_README.md` | Human review template |

## Model matrix

CLI tokens: `stub`, `ollama`, `ollama:llama3.2:1b`, or a JSON matrix:

See [`benchmarks/matrix.example.json`](../benchmarks/matrix.example.json).

```bash
uv run payloq bench --models stub --out runs/benchmark
uv run payloq bench --models stub,ollama:llama3.2:1b --out runs/benchmark
uv run payloq bench --config benchmarks/matrix.example.json --out runs/benchmark
uv run payloq bench --models stub --judge --out runs/benchmark_judge
```

CPU-friendly default Ollama tag: `llama3.2:1b`. Models shortlist is still open — stubs are valid for CI.

## Graders (code)

- **Parameters:** `payloq_benchmark.graders.grade_parameters`
- **Reading / MoM:** `grade_probes` over `DEFAULT_PROBES`
- **Interpretation:** `grade_interpretation` (heuristic rubric)
- **Judge (optional):** `payloq_benchmark.judge.run_llm_judge`

## Windows (Anmol Desktop)

Blank line between each command:

```powershell
cd C:\Users\anmol\Desktop\PayLoq

uv sync

uv run payloq bench --models stub --out runs\benchmark

uv run payloq bench --models stub,ollama:llama3.2:1b --out runs\benchmark_matrix

uv run payloq bench --config benchmarks\matrix.example.json --out runs\benchmark_cfg
```

Ollama install steps: [ollama-windows.md](ollama-windows.md).

# Evaluation (benchmark + Ollama scorecard)

Work order §3 metrics live in `packages/benchmark` and are driven by `payloq bench`.

## What is scored

| Metric | How |
| --- | --- |
| Parameter correctness | Code grader vs scenario `parameters_from_language_model` answer key |
| Figure reading | Code-checked numeric probes (`cash_end`, `revenue_last`, first negative projection week) |
| MoM change | Probe on `mom_revenue_change` from monthly reports |
| Interpretation quality | Rubric: factual / understandable / no invented causes; optional LLM judge; human spot-check CSV |
| **FI quality band** | Separate score for Finnish markers on FI prompts — EN-only models are **not failed** on the main interpretation rubric |
| Latency / tokens / hardware | Per-call adapter metrics + `hardware.json` |
| Rough cost | Local energy proxy from tokens + wall time (`rough_cost_eur`) |

**Principle:** packs used for reading/interpretation are generated from the **answer-key parameters** (code calculates). Models are graded on extraction from NL and on reading/interpreting ready-made figures.

## Finnish scoring band (EN-only models)

Finnish is required for the PoC, but many open finance models are EN-primary. Policy:

1. Main interpretation score stays language-agnostic (figures + no invented causes).
2. `fi_quality_score` is a **separate band** on FI prompts (`grade_fi_quality`).
3. Bands: **high** ≥ 0.75 · **mid** 0.40–0.75 · **low** < 0.40 · **n/a** (EN prompt / skipped).
4. EN-only answers on FI questions → low FI band; they still appear on the scorecard.

## Artifacts under `runs/benchmark/` (gitignored)

| File | Purpose |
| --- | --- |
| `results.json` | Full run log + per-field grade detail |
| `scorecard.json` | Aggregates by model + FI band legend + skipped models |
| `scorecard.csv` | Same aggregates for Excel |
| `runs.csv` | Flat per model×scenario rows |
| `metrics.sqlite` | SQLite store (`benchmark_runs` table) |
| `hardware.json` | Platform fingerprint |
| `pack_summary_<scenario>.json` | Figures shown to models |
| `spotcheck.csv` + `spotcheck_README.md` | Human review template |

## CPU model shortlist

Official config: [`benchmarks/matrix.cpu.json`](../benchmarks/matrix.cpu.json)

| Tier | Model | Notes |
| --- | --- | --- |
| baseline | `stub` | Always works (CI / offline) |
| recommended | `llama3.2:1b` | Default CPU-friendly live model |
| optional | `llama3.2:3b` | Larger step-up when Desktop has headroom |
| optional | `qwen2.5:3b` | Second size for multilingual / FI probes |

Minimal example (stub + recommended only): [`benchmarks/matrix.example.json`](../benchmarks/matrix.example.json).

When Ollama is down, `skip_unavailable` (default **on**) skips live cells; stub still runs.

## CLI

```bash
uv run payloq bench --models stub --out runs/benchmark
uv run payloq bench --models shortlist --out runs/benchmark_cpu
uv run payloq bench --models shortlist:recommended --out runs/benchmark_rec
uv run payloq bench --config benchmarks/matrix.cpu.json --out runs/benchmark_cpu
uv run payloq bench --models stub --judge --out runs/benchmark_judge
```

## Windows one-liners (Anmol Desktop)

Prefer a single line with ` & ` (chat paste often strips newlines):

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & git pull origin main & uv sync & uv run payloq bench --models stub --out runs\benchmark
```

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & ollama pull llama3.2:1b & uv run payloq bench --models shortlist:recommended --out runs\benchmark_rec
```

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & ollama pull llama3.2:1b & ollama pull llama3.2:3b & ollama pull qwen2.5:3b & uv run payloq bench --config benchmarks\matrix.cpu.json --out runs\benchmark_cpu
```

Ollama install steps: [ollama-windows.md](ollama-windows.md).

## Graders (code)

- **Parameters:** `payloq_benchmark.graders.grade_parameters`
- **Reading / MoM:** `grade_probes` over `DEFAULT_PROBES`
- **Interpretation:** `grade_interpretation`
- **FI band:** `grade_fi_quality`
- **Judge (optional):** `payloq_benchmark.judge.run_llm_judge`

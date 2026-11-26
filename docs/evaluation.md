# Evaluation (benchmark + Ollama scorecard)

Work order §3 metrics live in `packages/benchmark` and are driven by `payloq bench`.

## What is scored

| Metric | How |
| --- | --- |
| Parameter correctness | Code grader vs scenario `parameters_from_language_model` answer key |
| Figure reading | Code-checked numeric probes (`cash_end`, `revenue_last`, first negative projection week) |
| MoM change | Probe on `mom_revenue_change` from monthly reports |
| Interpretation quality | Rubric: factual / understandable / **grounded** / no invented causes / **no contradiction**; optional LLM judge; human spot-check CSV |
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

## CPU / Task B model shortlist

- Mac-friendly default: [`benchmarks/matrix.cpu.json`](../benchmarks/matrix.cpu.json)
- Full Task B catalog (general + finance + exclusions): [`benchmarks/models.task_b.md`](../benchmarks/models.task_b.md) · [`benchmarks/matrix.task_b.json`](../benchmarks/matrix.task_b.json)

| Tier | Model | Notes |
| --- | --- | --- |
| baseline | `stub` | Always works (CI / offline); excluded from comparisons |
| general | `qwen2.5:0.5b` / `3b` / `7b` | Default pack = 7b; FI band separate |
| general | `llama3.2:1b` / `3b`, `llama3.1:8b` | Size ladder incl. 8B step-up |
| general | `mistral:7b`, `phi3:mini`, `gemma2:2b` / `9b` | Other families (9b heavy on Mac) |
| finance | `FableForge-AI/nexus-finance:q4_k_m` | Open finance-tuned (~1.5B); FI band separate |
| finance | FinGPT GGUF (`hf.co/gaianet/…`) | Optional — verify HF license; schema-format risk |
| excluded | FinTral, FinBERT, FinMA (until GGUF) | See `models.task_b.md` |
| cloud | Claude API | Synthetic data only — not wired yet |

Minimal example (stub + sizes + finance): [`benchmarks/matrix.example.json`](../benchmarks/matrix.example.json).

When Ollama is down, `skip_unavailable` (default **on**) skips live cells; stub still runs. Judge (when `--judge`) is skipped the same way — never stubbed as a judge.

Seeded Task B scorecard (human-readable + Mac commands): Project store `docs/task-b-seeded-scorecard.md`; committed copies under `reports/task-b-*`.

### PL-52 — per Generate compare

`POST /api/generate/from-text` accepts `compare` (default true) and `compare_models` (default Mac winners: `qwen2.5:3b`, `llama3.2:3b`, `qwen2.5:7b`). After the pack is built, each selected model is scored on the **same** code figures; results land in `comparison.json` on the run and in the Run detail UI.

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
cd /d C:\Users\anmol\Desktop\PayLoq & ollama pull llama3.2:1b & ollama pull llama3.2:3b & ollama pull qwen2.5:3b & ollama pull qwen2.5:7b & ollama pull FableForge-AI/nexus-finance:q4_k_m & uv run payloq bench --config benchmarks\matrix.cpu.json --out runs\benchmark_cpu --judge
```

Ollama install steps: [ollama-windows.md](ollama-windows.md).

## Mac one-liners (Compose Ollama — `~/Desktop/PayLoq`)

Full Task B live matrix + judge (see also [ollama-mac.md](ollama-mac.md) and Project store `docs/task-b-seeded-scorecard.md`):

```bash
cd ~/Desktop/PayLoq && git pull origin main && docker compose --profile ollama up --build -d
until curl -sf http://127.0.0.1:11434/api/tags >/dev/null; do sleep 2; done
docker compose --profile ollama exec ollama ollama pull llama3.2:1b
docker compose --profile ollama exec ollama ollama pull llama3.2:3b
docker compose --profile ollama exec ollama ollama pull qwen2.5:3b
docker compose --profile ollama exec ollama ollama pull qwen2.5:7b
docker compose --profile ollama exec ollama ollama pull FableForge-AI/nexus-finance:q4_k_m
PAYLOQ_OLLAMA_TIMEOUT=600 uv run payloq bench --config benchmarks/matrix.cpu.json --out runs/benchmark_task_b_mac --seed 42 --judge --spotcheck
```

## Graders (code)

- **Parameters:** `payloq_benchmark.graders.grade_parameters`
- **Reading / MoM:** `grade_probes` over `DEFAULT_PROBES`
- **Interpretation:** `grade_interpretation` (five fields; mean overall)
- **FI band:** `grade_fi_quality`
- **Judge (optional):** `payloq_benchmark.judge.run_llm_judge`
- **Adversarial fixtures:** [`benchmarks/adversarial_answers.json`](../benchmarks/adversarial_answers.json) — deliberately wrong answers that must score well below 1.0 (`tests/test_grader_adversarial.py`)

### Stub scores of 1.0 = pipeline wiring only

The `stub` adapter answers reading probes by echoing `pack_summary` JSON and builds interpretation text from the same figures. A perfect stub reading/interpretation score therefore **only proves the harness is wired** (figures → adapter → graders), not that a model “understands” the pack. Live Ollama cells, the Finnish quality band, and human spot-check remain the real quality signal (Anmol Mac, PL-30).

### Interpretation rubric (hardened)

| Field | Fail when… |
| --- | --- |
| `understandable` | Answer too short |
| `factual` | Does not cite any pack figure |
| `grounded` | Money-like amounts in the answer are not in the pack (invented €) |
| `no_invented_causes` | Unsupported causal tropes (fraud, konkurssi/konkurssissa, bank freeze, …) |
| `no_contradiction` | Claims cash already/always negative (or a negative week) when the pack disagrees |

### Field-by-field wrong-answer check (for Anmol)

Use the pack in `benchmarks/adversarial_answers.json` (`cash_end=330000`, `revenue_last=210000`, `mom_revenue_change=1600`, `first_negative_projection_week=null`):

| Field | Wrong answer | Graders must… |
| --- | --- | --- |
| `reading.cash_end` | `{"value": 1}` | score ≪ 1.0 |
| `reading.revenue_last` | `{"value": 999999}` | score ≪ 1.0 |
| `reading.mom_revenue_change` | `{"value": -99999}` | score ≪ 1.0 |
| `reading.first_negative_projection_week` | `{"value": 7}` | score 0.0 (pack is null) |
| `interpretation.no_invented_causes` | “…customer fraud and a bank freeze…” | field 0.0; overall below 1.0 |
| `interpretation.grounded` / `factual` | cash 999999 / revenue 888888 | both 0.0; overall well below 1.0 |
| `interpretation.no_contradiction` | “kassa on jo negatiivinen joka viikko” (while citing 330000) | field 0.0; overall below 1.0 |

```bash
uv run pytest tests/test_grader_adversarial.py -q
```

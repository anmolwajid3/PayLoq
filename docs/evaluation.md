# Evaluation notes (Phase 3 scaffold)

Benchmark metrics (work order §3) planned for the harness in `packages/benchmark`:

| Metric | How |
| --- | --- |
| Parameter correctness | Code grader vs scenario answer key |
| Figure reading / MoM change | Code-checked numeric probes |
| Interpretation quality | Rubric + optional LLM judge + human spot check |
| Latency / tokens / hardware | Adapter run logs |
| Cost-effectiveness | Derived from tokens + hardware class |

Phase 1 ships `payloq bench` with the **stub** adapter only (CPU, no GPU). Wire Ollama / other local runtimes when models are shortlisted.

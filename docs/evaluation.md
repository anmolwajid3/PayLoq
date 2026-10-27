# Evaluation notes (Phase 3 scaffold)

Benchmark metrics (work order §3) planned for the harness in `packages/benchmark`:

| Metric | How |
| --- | --- |
| Parameter correctness | Code grader vs scenario answer key |
| Figure reading / MoM change | Code-checked numeric probes |
| Interpretation quality | Rubric + optional LLM judge + human spot check |
| Latency / tokens / hardware | Adapter run logs |
| Cost-effectiveness | Derived from tokens + hardware class |

Phase 1–2 ship `payloq bench` with the **stub** adapter by default (CPU, no GPU). Phase 2 also wires `OllamaAdapter` (`llama3.2:1b` default) into `payloq generate --from-text --llm ollama`. Full model-matrix scoring remains Phase 3 once a shortlist exists.

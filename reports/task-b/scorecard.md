# Task B seeded scorecard (committed copy)

Batch `93b544893573` · cloud seed with Ollama (Europe/Helsinki).

Stub excluded from comparisons. Unpulled tags now skip (this batch still has empty cells for 3b/7b — Mac must pull).


## Aggregates (by_model)

| model | param | read | MoM | interp | FI | FI band | latency_ms | tokens | cost_eur |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| `ollama:FableForge-AI/nexus-finance:q4_k_m` | 0.068 | 0.333 | 1.0 | 0.400 | 0.000 | low | 1624907 | 9070 | 0.04505 |
| `ollama:llama3.2:1b` | 0.068 | 0.332 | 1.0 | 0.933 | 0.750 | high | 1185516 | 10808 | 0.03304 |

## Per scenario (pulled models only)

| model | scenario | param | read | MoM | interp | FI | latency_s |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `ollama:llama3.2:1b` | good | 0.0909 | 0.3333 | 1.0 | 0.8 | 1.0 | 2445.6 |
| `ollama:llama3.2:1b` | weak | 0.0 | 0.3305 | 1.0 | 1.0 | 0.75 | 2429.1 |
| `ollama:llama3.2:1b` | cash_critical | 0.0 | 0.3333 | 1.0 | 1.0 | 0.5 | 974.7 |
| `ollama:FableForge-AI/nexus-finance:q4_k_m` | good | 0.0909 | 0.0 | 1.0 | 0.4 | 0.0 | 3096.8 |
| `ollama:FableForge-AI/nexus-finance:q4_k_m` | weak | 0.0 | 0.6667 | 1.0 | 0.4 | 0.0 | 2455.6 |
| `ollama:FableForge-AI/nexus-finance:q4_k_m` | cash_critical | 0.0 | 0.3333 | 1.0 | 0.4 | 0.0 | 2475.0 |

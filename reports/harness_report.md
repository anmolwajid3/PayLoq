# Harness report

Tier: fixture. Command: `pytest tests/harness -q`.

Each cell is PASS or the failed check name. Checks: status, consistency, fidelity, sensitivity, repeatability, seed isolation, stub, ollama-unreachable.

| scenario | 1 | 2 | 3 | 42 | 99 |
| --- | --- | --- | --- | --- | --- |
| good | PASS | PASS | PASS | PASS | PASS |
| weak | PASS | PASS | PASS | PASS | PASS |
| cash_in_trouble | PASS | PASS | PASS | PASS | PASS |
| invoices_out_of_balance | PASS | PASS | PASS | PASS | PASS |
| cash_turning_critical | PASS | PASS | PASS | PASS | PASS |
| vague | PASS | PASS | PASS | PASS | PASS |
| fully_stated | PASS | PASS | PASS | PASS | PASS |
| partly_stated | PASS | PASS | PASS | PASS | PASS |
| one_off_inflow | PASS | PASS | PASS | PASS | PASS |
| no_one_off | PASS | PASS | PASS | PASS | PASS |
| annual_revenue | PASS | PASS | PASS | PASS | PASS |
| months_24 | PASS | PASS | PASS | PASS | PASS |
| finnish | PASS | PASS | PASS | PASS | PASS |
| stub | PASS | — | — | — | — |
| ollama-unreachable | PASS | — | — | — | — |

## Failures

No failures.

## Module-level caches

- `apps/api/src/payloq_api/config.py:53` get_settings
- `apps/api/src/payloq_api/db.py:11` _engine
- `packages/schemas/src/payloq_schemas/field_map.py:60` load_field_map

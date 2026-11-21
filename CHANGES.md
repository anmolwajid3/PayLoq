# CHANGES — Pilot generator work-order fix (Task A)

Source: `internal/pilot-generator-fix-prompt.md` + `docs/payloq-pilot-work-order.pdf`.
PDF conflict check: none found (journal is §4 optional; schema may evolve; fidelity/consistency are code checks). No `OPEN_QUESTIONS.md`.

Scope: Task A generator only. Benchmark (Task B) and chat demo kept, with **labelling rules** only (Option A). Journal deleted. One-off direction canonicalized to `inflow|outflow`.

---

## Labelling rules (Option A)

| Area | Rule |
| --- | --- |
| Task B / benchmark | Stub runs are labelled **`stub, not a model`** (notes + detail). Stub rows are **excluded from scorecard / `by_model` comparisons**. Stub remains available as a baseline harness cell. |
| Chat demo | When the active adapter is stub (or fallback lands on stub), the header / `llm_adapter` is **`stub`**. **Never** attach an Ollama model name to stub answers (`llm_model` is null). |
| Task A generate | Ollama only. No `StubLlmAdapter`, no `FallbackAdapter`, no keyword-heuristic extract success path. |

---

## A. Local model (Ollama-only extract)

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/llm/src/payloq_llm/defaults.py` | `DEFAULT_OLLAMA_MODEL` | Default `qwen2.5:7b` (not `llama3.2:1b`). Host stays `http://127.0.0.1:11434`. |
| `apps/api/src/payloq_api/config.py` | `Settings.ollama_model` | Default `qwen2.5:7b` from config/env. |
| `packages/llm/src/payloq_llm/adapters.py` | `OllamaAdapter.__init__`, `_chat` | Temp 0; fixed seed in `options`; pass section-B JSON schema as `format` (not bare `"json"`). Log model, latency, tokens. |
| `packages/llm/src/payloq_llm/adapters.py` | `OllamaAdapter.extract_parameters` | Ollama-only; **3 model calls total** (1 initial + 2 retries) then raise (status error). No stub fallback. |
| `packages/llm/src/payloq_llm/adapters.py` | `get_adapter` | Generator path: never wrap ollama with stub. Stub adapter remains for Task B / chat only. |
| `packages/llm/src/payloq_llm/adapters.py` | `input_from_text`, `input_from_descriptions` | Require Ollama adapter; reject stub / unwrap FallbackAdapter. |
| `apps/api/src/payloq_api/services/generate.py` | `run_from_text` | Ollama only; on extract failure → `status=error`, no data files. |
| `apps/cli/src/payloq_cli/main.py` | `generate` | From-text: Ollama only. |

## B. Extraction schema

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/llm/src/payloq_llm/extraction_schema.py` | **new** `EXTRACTION_JSON_SCHEMA`, `extraction_format_schema()` | Section B JSON Schema for Ollama `format`. |
| `packages/llm/src/payloq_llm/prompts.py` | `PARAM_SCHEMA_HINT`, `parameter_extraction_prompt`, repair prompts | Prompt matches section B (`scenario_shape`, `stated` quotes, `parameters` with WO field names). Null if unstated; never 0 for unstated. |
| `packages/schemas/src/payloq_schemas/models.py` | `OneOffCashEvent.direction` | Canonical **`inflow \| outflow` only** (legacy `in`/`out` accepted then normalized). |
| `packages/llm/src/payloq_llm/assume.py` / `stated_checks.py` / `params_clamp.py` / `engine.py` | one-off direction | Persist and apply `outflow` / `inflow` everywhere. |

## C. Code checks on extraction

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/llm/src/payloq_llm/stated_checks.py` | `check_stated_values` (was quote match), `scan_description_numbers`, `clean_extraction_output`, `enforce_required_one_offs` | **TC-ABC:** value-based grounding (not quote-string); clean brackets/unmentioned zeros; stated+null → warn+demote; required one-offs fail if missing/wrong direction. Growth ∈ [-0.2, 0.2]; direction inflow\|outflow. |
| `packages/llm/src/payloq_llm/extract_pipeline.py` | `finalize_extracted_parameters` | Wire B→clean→C value ground→D; enforce description one-offs; upgrade under-classified shapes to `cash_critical` when NL looks cash-critical (TC-A projection fall). |
| `packages/llm/src/payloq_llm/prompts.py` | repair prompts | Quotes optional; value must appear in description. |
| `packages/llm/src/payloq_llm/defaults.py` / `Generate.tsx` | UI + shortlist | Default/header model `qwen2.5:7b` (no silent substitute). |

## D. Unstated values (code assume)

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/schemas/src/payloq_schemas/scenario_shape_ranges.py` | config table | Neutral + optional industry ranges; `scenario_shape` selects growth/starting-cash bands. |
| `packages/llm/src/payloq_llm/assume.py` | `apply_assumed_defaults` | Always assume nulls (incl. `starting_cash_eur`). Mark `source: assumed` \| `stated`. |

## E. Output

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/generator/src/payloq_generator/engine.py` | `write_pack` | JSON + xlsx + answer_key + run_log; **never** journal. |
| `packages/export_xlsx/src/payloq_export_xlsx/writer.py` | `write_scenario_xlsx` | Income/Balance/History/Invoices/Projection + Assumptions. Journal sheet removed. |
| `packages/generator/src/payloq_generator/pipeline.py` | `run_generation` | No `write_journal` parameter. |

## F. Validation (consistency + fidelity)

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/validate/src/payloq_validate/checks.py` | `validate_pack` | Consistency + fidelity blocking; `projection_history_scale` warning only. |
| `packages/validate/src/payloq_validate/fidelity.py` | `check_fidelity` | Blocking stated-value match. |

## F2. Generic field map (fidelity + Run summary)

One config table drives every extraction-schema field → `input.json` location, Run summary label, and fidelity rule. No test-/description-specific branches; no hard-coded example amounts.

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/schemas/.../field_map.json` | **new** config | Rows for every section-B parameter (`revenue_monthly_eur`, `starting_cash_eur`, `covenant_min_cash_eur`, growth, DSO/DPO, `one_off_events` amount/month/direction, industry, company_size, …). |
| `packages/schemas/.../field_map.py` | `load_field_map`, `build_field_summary_rows` | Load map; build summary rows; B↔engine helpers from map. |
| `packages/validate/.../fidelity.py` | `check_fidelity` | Loops **only** over map rows; mismatch / missing output → `error` naming field + stated + output. |
| `packages/llm/.../extract_pipeline.py` | `finalize_extracted_parameters` | `stated_values` / B→engine from map; keep industry/company_size in `stated_values` for fidelity. |
| `packages/llm/.../assume.py` | `apply_assumed_defaults` | Target assumed independently when unstated; **no** covenant→target copy. Target→covenant fill only. |
| `apps/api/.../generate.py` | `_pack_summary` | Adds `field_summary` from the map. |
| `apps/web/.../fieldSummary.ts` + RunDetail / PDF / ArtifactViewer | display | Run summary renders every map row under that row’s label only. |
| `tests/test_generic_field_map.py` | property tests | Random per-field / swap / mutate / unstated cases (no fixed example values). |

### F2 follow-up (evidence round 2)

| File | Change |
| --- | --- |
| `packages/schemas/.../field_map.py` | `build_field_summary_rows` marks industry/company_size `stated` via `stated_values` / `field_sources`. |
| `packages/llm/.../extract_pipeline.py` | Option stated fields recorded in `field_sources`. |
| `packages/llm/.../assume.py` / `stated_checks.map_b_parameters_to_engine` / `models._accept_wo_aliases` | Removed covenant→target_cash mirror. |
| `tests/test_generic_field_map.py` | Property tests for industry/company_size summary source; covenant≠target when only covenant stated. |

## G. Removals (finish)

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/generator/src/payloq_generator/journal.py` | **deleted** | Removed entirely (not moved). |
| `packages/schemas/.../models.py` | `JournalLine` / `JournalEntry` / `JournalEntries` | Removed from schema + `ScenarioPack`. |
| `apps/api/.../routers/runs.py` | `POST /runs/{id}/journal` | Removed. |
| `apps/api/.../services/chat.py` | `ensure_journal_artifact` | Removed; pack load ignores journal files. |
| `apps/web/.../ArtifactViewer.tsx` | `JournalPackView` | Removed. |
| `apps/web/.../api.ts` / `i18n.ts` | `write_journal` / journal strings | Removed. |
| Generate path | stub / FallbackAdapter / keyword extract | Scrubbed from API generate + CLI generate. |

## Task B / chat labelling (only)

| File | Change |
| --- | --- |
| `packages/benchmark/.../runner.py` | Stub notes = `stub, not a model`; exclude stub from scorecard `by_model`. |
| `packages/llm/.../chat_demo.py` | Stub / stub-fallback → `llm_adapter="stub"`. |
| `apps/api/.../services/chat.py` | `result_to_dict` clears `llm_model` when adapter is stub. |
| `apps/web/.../ChatDemo.tsx` | Header shows `stub` when stub active. |

## H. Tests

| File | Change |
| --- | --- |
| `tests/test_pilot_generator_h.py` | H1–H8. |
| `tests/test_param_grounding.py` | REG-RUN17 / REG-REVENUE-SCALE (Run #17 grounding + raw-vs-parsed). |
| `tests/test_srs_must.py` / scenario validators | TC-style scenario checks (good/weak/cash_critical/invoices_out_of_balance). |
| Journal / generate-stub tests | Updated for deletion and Ollama-only generate. |

---

## Explicit non-goals
- No Task B harness redesign beyond stub labelling / comparison exclusion.
- No chat-demo feature work beyond journal removal + stub labelling.
- No guessing beyond PDF + form prompt + Option A decision.

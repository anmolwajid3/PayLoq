# CHANGES — Pilot generator work-order fix (Task A)

Source: `internal/pilot-generator-fix-prompt.md` + `docs/payloq-pilot-work-order.pdf`.
PDF conflict check: none found (journal is §4 optional; schema may evolve; fidelity/consistency are code checks). No `OPEN_QUESTIONS.md`.

Scope: Task A generator only. Benchmark (Task B) and chat demo left alone except where stub/fallback must stop feeding the generator path. Journal UI card removed as listed.

---

## A. Local model (Ollama-only extract)

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/llm/src/payloq_llm/defaults.py` | `DEFAULT_OLLAMA_MODEL` | Default `qwen2.5:7b` (not `llama3.2:1b`). Host stays `http://127.0.0.1:11434`. |
| `apps/api/src/payloq_api/config.py` | `Settings.ollama_model` | Default `qwen2.5:7b` from config/env. |
| `packages/llm/src/payloq_llm/adapters.py` | `OllamaAdapter.__init__`, `_chat` | Temp 0; fixed seed in `options`; pass section-B JSON schema as `format` (not bare `"json"`). Log model, latency, tokens. |
| `packages/llm/src/payloq_llm/adapters.py` | `OllamaAdapter.extract_parameters` | Ollama-only; 2 retries then raise (status error). No stub fallback. |
| `packages/llm/src/payloq_llm/adapters.py` | `get_adapter` | Generator path: `fallback_stub=False` for ollama; refuse using stub for from-text extract. |
| `packages/llm/src/payloq_llm/adapters.py` | `FallbackAdapter`, `StubLlmAdapter.extract_parameters` | Remove from generator pipeline (no `ollama->stub`). Stub class may remain only for Task B / fixtures — not imported by generate path. |
| `packages/llm/src/payloq_llm/adapters.py` | `input_from_text`, `input_from_descriptions` | Require Ollama adapter; do not default to `StubLlmAdapter`. Drop keyword NL repair that invents params. |
| `apps/api/src/payloq_api/services/generate.py` | `run_from_text` | Always `fallback_stub=False`; on extract failure → `status=error`, no data files, no stub. |
| `apps/cli/src/payloq_cli/main.py` | `generate` | From-text: Ollama only, no `--fallback-stub` success path. |

## B. Extraction schema

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/llm/src/payloq_llm/extraction_schema.py` | **new** `EXTRACTION_JSON_SCHEMA`, `extraction_format_schema()` | Section B JSON Schema for Ollama `format`. |
| `packages/llm/src/payloq_llm/prompts.py` | `PARAM_SCHEMA_HINT`, `parameter_extraction_prompt`, repair prompts | Prompt matches section B (`scenario_shape`, `stated` quotes, `parameters` with WO field names). Null if unstated; never 0 for unstated. |
| `packages/schemas/src/payloq_schemas/models.py` | **new** `ModelExtraction`, `ExtractionParameters`, update `ExtractedParameters` / `ParametersFromLanguageModel` | Model for B shape; store `scenario_shape`, `scenario_shape_quote`, `stated` quotes, `field_sources`, conversion notes. |
| `packages/llm/src/payloq_llm/parse.py` | `extract_json_object` / validate | Validate against B schema. |

## C. Code checks on extraction

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/llm/src/payloq_llm/stated_checks.py` | **new** `check_stated_quotes`, `apply_annual_to_monthly`, growth/one-off validators | Quote ⊆ description (case-insensitive); value in quote after unit parse; retry once then error naming field. Annual→monthly in code. Growth ∈ [-0.2, 0.2]. One-offs: month 1..months, direction inflow\|outflow. |
| `packages/llm/src/payloq_llm/grounding.py` | `ground_stated_parameters` | Align to stated-quote rules (only fields listed in `stated`); stop rejecting unstated zeros by forcing nulls upstream. |
| `packages/llm/src/payloq_llm/extract_pipeline.py` | `finalize_extracted_parameters`, `extract_with_grounding_retry` | Wire B→C→D; map WO names ↔ legacy engine names. |

## D. Unstated values (code assume)

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/schemas/src/payloq_schemas/scenario_shape_ranges.py` | **new** config table | Neutral + optional industry ranges; `scenario_shape` selects growth/starting-cash bands (e.g. `cash_critical` → trough ~3 weeks). |
| `packages/schemas/src/payloq_schemas/industry_defaults.py` | `draw_assumed_defaults` | Consume scenario_shape ranges; no company-specific hardcodes. |
| `packages/llm/src/payloq_llm/assume.py` | `apply_assumed_defaults`, `MissingRequiredParameterError` | Always assume nulls (incl. `starting_cash_eur`); **remove** Missing-required rule / `require_starting_cash`. Mark `source: assumed` \| `stated` + quotes. |
| `packages/schemas/src/payloq_schemas/constants.py` | `REQUIRED_STATED_FIELDS` | Remove (or empty). |

## E. Output

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/generator/src/payloq_generator/engine.py` | `write_pack` | Persist params, sources, quotes, model name, seed, `scenario_shape` in `input.json`; keep monthly/cash/answer_key; **never** write `journal_entries.json`. On error path: no data files. |
| `packages/export_xlsx/src/payloq_export_xlsx/writer.py` | `write_scenario_xlsx`, `_journal_sheet` | Tabs: Income/Balance/History/Invoices/Projection + Assumptions. Drop Journal sheet. Keep Scenario sheet as non-normative mirror of input (PDF allows structure). |
| `packages/generator/src/payloq_generator/pipeline.py` | `run_generation` | Default `write_journal=False`; error → no data files. |

## F. Validation (consistency + fidelity)

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/validate/src/payloq_validate/checks.py` | `validate_pack`, `ValidationResult` | Separate consistency vs fidelity issue groups; `ok` only if both pass (plus model success). `projection_history_scale` warning only. |
| `packages/validate/src/payloq_validate/fidelity.py` | **new** `check_fidelity` | Blocking: every `stated` value equals matching output param field. |
| `packages/generator/src/payloq_generator/pipeline.py` | `run_generation` | Run fidelity; status error with reasons if fail. |
| `packages/generator/src/payloq_generator/consistency.py` | `check_parameters_consistency` | Keep blocking pre-gen checks; growth band align to ±0.2 where needed. |

## G. Removals

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/llm/src/payloq_llm/adapters.py` | Stub keyword heuristics in extract; `FallbackAdapter` on generate | Out of pipeline. |
| `packages/llm/src/payloq_llm/nl_cash_intent.py` | `looks_cash_critical`, `repair_params_from_nl` | Not used by generate path (fixtures/tests only if still needed). |
| `packages/llm/src/payloq_llm/nl_param_hints.py` | `looks_bakery`, `looks_steel_or_manufacturing`, inventing suggest_* | Not imported by pipeline. |
| `packages/llm/src/payloq_llm/nl_stated.py` | hybrid code-first merge used as stub substitute | Do not use as generator success path when Ollama fails. |
| `packages/generator/src/payloq_generator/journal.py` | `build_journal_entries` | Stop calling from pipeline/API/UI. |
| `apps/api/src/payloq_api/routers/runs.py` | journal POST | Remove or no-op journal endpoint wiring used by UI. |
| `apps/api/src/payloq_api/services/chat.py` | journal ensure helpers | Stop building journal for runs. |
| `apps/web/src/pages/RunDetail.tsx` | journal card / `ensureJournal` | Remove UI card. |
| `apps/web/src/api.ts` | `ensureJournal`, `write_journal` | Remove. |
| `apps/web/src/components/ArtifactViewer.tsx` | `JournalPackView` | Remove journal view path (or leave dead-code-free). |
| `apps/web/src/i18n.ts` | journal strings | Remove unused. |

## H. Tests

| File | Change |
| --- | --- |
| `tests/test_pilot_generator_h.py` | **new** H1–H8 (vague, fully stated, run23, run27, stub/unreachable, invalid JSON, two-value, repeatability). Report stated field actuals. |
| Existing tests that require stub fallback / MissingRequired / journal | Adjust or mark so generator path matches A–G; Task B stub tests untouched where possible. |

---

## Explicit non-goals
- No Task B benchmark harness redesign.
- No chat-demo feature work beyond journal removal touchpoints.
- No guessing beyond PDF + this prompt.

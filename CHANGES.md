# CHANGES — Pilot generator work-order fix (Task A) + Task B seed

Source: `internal/pilot-generator-fix-prompt.md` + `docs/payloq-pilot-work-order.pdf`.
PDF conflict check: none found (journal is §4 optional; schema may evolve; fidelity/consistency are code checks). No `OPEN_QUESTIONS.md`.

Scope: Task A generator + Task B seeded scorecard (PL-51). Chat demo labelling rules (Option A) unchanged. Journal deleted. One-off direction canonicalized to `inflow|outflow`.

---

## Task B — Seeded multi-model scorecard (PL-51)

| File | Change |
| --- | --- |
| `benchmarks/matrix.cpu.json` | Size ladder (`llama3.2:1b/3b`, `qwen2.5:3b`) + recommended `qwen2.5:7b` + finance `FableForge-AI/nexus-finance:q4_k_m`. Judge model → `qwen2.5:7b`. Live cells `fallback_stub: false`. |
| `benchmarks/matrix.example.json` | Same finance tag + judge; no placeholder `REPLACE_WITH_…`. |
| `packages/benchmark/.../config.py` | Ollama `ModelSpec` / CLI tokens default `fallback_stub=False` (no stub-contaminated scorecard cells). |
| `packages/benchmark/.../runner.py` | Skip LLM judge when Ollama unavailable (never stub-as-judge). Skip ollama cells when the **tag is not pulled** (host-up alone is not enough). |
| `docs/evaluation.md` | CPU shortlist table + Task B artifact pointers. |
| `reports/task-b/*` | Seeded scorecard JSON/CSV/MD + spotcheck from cloud live batch `93b544893573` (stub excluded; Mac still owns full ladder + judge). |
| `tests/test_benchmark_stub.py` | Matrix expects finance tier + stronger judge model. |

Human-readable store copy: Project `docs/task-b-seeded-scorecard.md` (+ gap inventory `docs/task-b-gap.md`).

## Task B — Per-input model comparison (PL-52)

| File | Change |
| --- | --- |
| `packages/llm/.../defaults.py` | `DEFAULT_COMPARE_MODELS` = Mac winners `qwen2.5:3b`, `llama3.2:3b`, `qwen2.5:7b`. |
| `apps/api/.../services/model_compare.py` | **new** — score shortlist on one code-built pack; write `comparison.json` + `compare_answers/`. |
| `apps/api/.../services/generate.py` | `run_from_text(..., compare=, compare_models=)` runs compare after a successful pack. |
| `apps/api/.../schemas.py` / `routers/runs.py` | Request fields + `RunOut.comparison`; `/llm/models` returns `compare_shortlist`. |
| `apps/web/.../Generate.tsx` | Multi-select compare checkboxes (defaults = shortlist ∩ installed). |
| `apps/web/.../RunDetail.tsx` | Comparison table + recommended badge + expandable answers. |
| `tests/test_model_compare_pl52.py` | Unit tests for shortlist + stub scoring on a preset pack. |

## Background Generate + progress %

| File | Change |
| --- | --- |
| `apps/api/.../services/progress.py` | **new** — `progress.json` percent/stage helpers. |
| `apps/api/.../services/generate.py` | `create_from_text_run` + `execute_from_text_job`; stage updates through extract → pack → compare. |
| `apps/api/.../routers/runs.py` | `background=true` (default) returns `status=running` and finishes via `BackgroundTasks`. |
| `apps/api/.../schemas.py` | `GenerateFromTextRequest.background`; `RunOut.progress`. |
| `apps/web/.../Generate.tsx` / `RunDetail.tsx` | Navigate immediately; poll run every 1.5s and show progress bar. |
| `tests/test_background_progress.py` | Progress helpers + background enqueue smoke test. |

## PL-53 / PL-54 / PL-55 follow-ons

| File | Change |
| --- | --- |
| `packages/llm/.../defaults.py` | Size-ladder `DEFAULT_COMPARE_MODELS` (1b→3b→7b); `DEFAULT_JUDGE_MODEL`; finance tag constant. |
| `apps/api/.../model_compare.py` | LLM judge on interpretations; score rationale; finance tag when pulled. |
| `apps/web/.../exportRunPdf.ts` | Full-package PDF: comparison table, judge who/why, per-model rationale + answers. |
| `apps/web/.../RunDetail.tsx` | Judge column + rationale in compare UI. |
| `apps/api/.../generate.py` + preset router | Preset compare + optional background (PL-55). |
| Project `docs/task-b-followons.md` | Gap map + order. |

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

## F3. Generic repeatability

Same input + seed + code → byte-identical `input.json` / `monthly_reports.json` / `cash_and_invoices.json` (in-process and fresh subprocess). No special-case inputs.

| File | Function / symbol | Change |
| --- | --- | --- |
| `packages/generator/.../engine.py` | `generate_pack`, `write_pack` | Sorted projection-assumption text; unlink stale data JSON before write (no previous-run file leak). |
| `packages/llm/.../extract_pipeline.py` | `finalize_extracted_parameters` | Sort `field_sources` / `field_quotes` / `stated_values` for stable `input.json` bytes. |
| `packages/llm/.../assume.py` | `apply_assumed_defaults` | Sorted provenance + stable cost-share key order. |
| `packages/validate/.../checks.py` | `_check_cash` | Blocking VR-07: last history == latest cash == last monthly cash. |
| `tests/test_repeatability_property.py` | **new** | 50 random descriptions × 3 in-process + 1 subprocess SHA-256; cash triangle; stale-dir clear. |

## F4. Stated-only model, derived in code

The extraction schema asks only for numbers written in the description. Annual totals, percent-to-decimal growth, and days from weeks or months are computed in code with source `derived` and the formula. Unstated model fields are null. No test-specific inputs.

| File | Change |
| --- | --- |
| `packages/llm/.../extraction_schema.py` | Drop `growth_per_month_fraction`. Add `growth_per_month_percent`, `dso_weeks`, `dpo_weeks`, `dso_months`, `dpo_months`. |
| `packages/llm/.../prompts.py` | Model must not calculate, convert, annualise, or infer. Null if not written. |
| `packages/llm/.../stated_only.py` | **new** formula table + stated-only cleanup. |
| `packages/llm/.../extract_pipeline.py` | Strip conversions, derive, record `derived_values` / `field_sources=derived`. |
| `packages/schemas/.../models.py` | `ParamSource` includes `derived`. Store percent, period counts, `derived_values`. |
| `packages/schemas/.../field_map.json` | Map matches the schema (web copy updated). Growth row is the written percent (`format: percent`, `numeric_near`). Weeks/months rows use `format: count`. |
| `packages/llm/.../assume.py` | When growth is assumed, also set `growth_per_month_percent` = fraction × 100 (source `assumed`). |
| `packages/llm/.../nl_cash_intent.py` | A lone `m` is not millions when it starts the word `month`/`months`. |
| `packages/llm/.../stated_checks.py` | Event months match `in month N`, not a DSO duration of `N months`. Literal number scan can skip percent/100 and thousands-group fragments. |
| `tests/test_stated_only_derived.py` | **new** 50 random subsets: unstated model fields null; derived values match formulas. |
| `tests/test_repeatability_property.py` | Descriptions state the percent, not the decimal. Cash triangle on every in-process and subprocess run. |

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

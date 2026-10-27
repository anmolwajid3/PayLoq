# Payloq pilot — technical plan

**Status:** proposal for approval (no implementation yet)  
**Source:** *Payloq pilot – Work order for the technical team* (PDF, 2 pages) + attached example datasets  
**Audience:** Anmol Wajid / technical team  

---

## 1. Product summary

Payloq (Ulvila, founded 2026) wants a **research PoC**, not a customer-facing finance product. The pilot proves two linked capabilities:

1. **Generator (Task A):** From a short everyday-language company situation plus a few options, produce **consistent synthetic financial datasets** (JSON + Excel) suitable for cases such as “cash turns critical in three weeks.”
2. **Benchmark (Task B):** Compare **locally run** language models as a “virtual accountant” on (a) turning a description into parameters and (b) interpreting generated figures in plain language—without inventing causes.

**Principle (work order §1–2):** *Code calculates; the language model interprets.* All figures and consistency checks are ordinary code. The LLM only: maps description → structured parameters, writes descriptive texts (names, invoice lines), and interprets ready-made figures.

**Users of this PoC:** Payloq technical/research staff and project partners evaluating models—not end-customer CFOs. Success is demonstrated when:

- Generated data passes automated balance/consistency checks and matches the spirit of the three attached scenarios (good / weak / cash critical).
- Benchmark metrics distinguish models on parameter correctness, figure reading, change detection, interpretation quality, speed/resources, and cost-effectiveness (work order §3).
- Everything remains **open source** and uses **only synthetic data** (work order §1).

Local models are mandatory for the primary evaluation path because financial data is sensitive; cloud models are optional **reference only**, and only on synthetic data (work order §3).

---

## 2. Functional scope

| Priority | Feature | Work-order anchor |
| --- | --- | --- |
| **Must** | Natural-language → structured parameters (revenue, margins/cost shares, growth, DSO/DPO, cash target, investments, etc.) | §2 Task A step 1 |
| **Must** | Deterministic generator: monthly P&L + balance sheet (12–24 months) | §2 Datasets |
| **Must** | Balance history (weekly) + open sales/purchase invoices + short cash projection from open invoices | §2 Datasets; examples |
| **Must** | Validators: BS balances; month-to-month continuity; cash vs history; receivables/payables vs open invoice sums | §2 Task A step 3; README |
| **Must** | Export JSON (system-agnostic) + Excel tabs (Scenario, Income statement, Balance sheet, Balance history, Open invoices, Projection) | §2 Output formats; example xlsx |
| **Must** | 3–5 ready-made scenario packs (examples already: good, weak, cash_critical; WO also mentions invoices out of balance) | §2 Ready-made scenarios |
| **Must** | Benchmark harness: same prompts/data across multiple local model sizes; parameter grading + interpretation grading | §3 |
| **Must** | Metrics: correctness, reading accuracy, change ID, interpretation quality, latency, tokens, hardware, cost-effectiveness | §3 Metrics |
| **Must** | Evaluation method: code-checked answer keys; optional stronger model as judge; human spot checks | §3 Evaluation method |
| **Must** | FI + EN descriptive text support; Finnish support tested separately for EN-only finance models | §3 Models; example `language: fi` |
| **Nice** | Chat demo on best model (“Why did cash drop…?”, “When does cash go negative…?”) | §4 If time allows |
| **Nice** | Accounting entries as an extra dataset | §4 |
| **Nice** | Finer control of volume/format of generated data | §4 |
| **Nice** | Optional cloud model as reference baseline | §3 |
| **Out of scope** | Real company data ingest, banking/payment APIs, production multi-tenant SaaS, GDPR processing of real personal/financial data | §1 (“not an application for any company”) |

---

## 3. Data model

Inferred from example JSON/XLSX (illustrative, not frozen—README and WO allow reshaping). Finnish VAT rate in examples: **25.5%** on receivables/payables/invoices; P&L lines are **VAT 0%**.

### 3.1 Generator input (`input.json`)

| Entity / field | Notes |
| --- | --- |
| `meta` | `fictional`, notes |
| `scenario_description` | `{ fi, en }` free text |
| `options` | `industry`, `company_size`, `months` (12–24), `language`, `currency` (EUR) |
| `parameters_from_language_model` | `monthly_revenue_start_eur`, `monthly_revenue_growth`, `cost_shares_of_revenue` (materials, services, personnel, other), `days_sales_outstanding`, `days_payables_outstanding`, `target_cash_at_end_eur`, `special_investment_eur`, `notes` |

### 3.2 Monthly reports (`monthly_reports.json`)

Per `month` (`YYYY-MM`):

- **Income statement:** `revenue`, `materials_and_services`, `personnel_costs`, `other_operating_costs`, `depreciation`, `operating_profit`, `interest_expense`, `profit_before_tax`, `income_tax`, `net_result`
- **Balance sheet — assets:** `fixed_assets`, `inventory`, `receivables`, `cash`, `total_assets`
- **Balance sheet — equity & liabilities:** `equity`, `loans`, `payables`, `other_current_liabilities`, `total_equity_and_liabilities`

**Invariant:** `total_assets == total_equity_and_liabilities`.

### 3.3 Cash & invoices (`cash_and_invoices.json`)

| Block | Fields |
| --- | --- |
| `meta` | `dataset`, `currency`, `scenario`, `as_of`, notes |
| `balance_history[]` | `date`, `balance` — **26 weeks** in examples |
| `open_invoices[]` | `id`, `type` (`sales`\|`purchase`), `counterparty`, `description`, `issue_date`, `due_date`, `amount_incl_vat`, `status` (`open`\|`overdue`) — **20** in examples |
| `projection_from_open_invoices[]` | `week`, `week_end`, `sales_inflow`, `purchase_outflow`, `projected_balance` — **8 weeks**; excludes payroll/tax/recurring; overdue sales assumed paid in week 1 |

**Cross-file invariants (examples satisfy):** last month cash = last balance history point; Σ open sales = receivables; Σ open purchases = payables.

### 3.4 Excel mirror

Sheets: Scenario | Income statement | Balance sheet | Balance history | Open invoices | Projection (bilingual FI/EN labels in examples).

### 3.5 Scenario I/O flow

```
NL description + options
    → LLM: parameters (+ later descriptive texts)
    → Code: months, cash history, invoices, projection
    → Code: validate
    → JSON + XLSX
    → Benchmark: (a) param extraction vs key  (b) interpretation vs figures/key
```

### 3.6 Benchmark artifacts (to define in schema)

- Prompt packs, model run logs (tokens, latency, hardware), scored parameter deltas, interpretation scores, judge outputs, human review notes.

---

## 4. Architecture

Recommended shape for a **local-first research PoC**:

```
┌─────────────────────────────────────────────────────────┐
│  CLI / thin local UI (optional chat later)              │
└──────────────┬──────────────────────────┬───────────────┘
               │                          │
               ▼                          ▼
┌──────────────────────────┐   ┌──────────────────────────┐
│  Generator service       │   │  Benchmark runner        │
│  - prompt → params (LLM) │   │  - model matrix          │
│  - params → datasets     │   │  - graders (code+judge)  │
│  - validators            │   │  - metrics store         │
│  - JSON/XLSX writers     │   │                          │
└──────────┬───────────────┘   └────────────┬─────────────┘
           │                                │
           ▼                                ▼
┌──────────────────────────┐   ┌──────────────────────────┐
│  Artifact store (files)  │   │  Local model runtime     │
│  scenarios/, runs/       │   │  (Ollama / vLLM / etc.)  │
└──────────────────────────┘   └──────────────────────────┘
```

- **API:** Optional thin FastAPI for UI/chat; MVP can be **CLI-only** (fits research PoC).
- **Jobs:** Benchmark runs are batch jobs (long-running, GPU-aware); generator is synchronous or short job.
- **Storage:** Filesystem artifacts + lightweight SQLite/DuckDB for run metrics; no need for heavy multi-tenant DB.
- **Integrations:** Local LLM runtime only for core path; optional OpenAI/Anthropic adapter gated to synthetic data.
- **UI:** Minimal: scenario browser + run results tables; chat demo only if time (§4).

---

## 5. Recommended stack

| Layer | Choice | Rationale |
| --- | --- | --- |
| Language | **Python 3.12+** | Financial generation, validation, Excel, LLM eval ecosystem; matches “code calculates” workload |
| Package layout | **uv** + monorepo packages | Fast, reproducible installs for research |
| Generator / validators | Pure Python + **Pydantic** schemas | Typed I/O matching JSON contracts; easy answer keys |
| Excel | **openpyxl** | Matches required xlsx tabs; already used in examples |
| API (optional) | **FastAPI** | Thin local API if UI/chat needed |
| UI (optional MVP+) | **Next.js** or simple **Streamlit/Gradio** | Prefer Streamlit/Gradio for PoC speed; Next.js only if Payloq wants product-shaped UI later |
| Local LLMs | **Ollama** (dev) + **vLLM** or llama.cpp (server GPU) | Local-first per WO; easy multi-size comparison |
| Eval / judging | Custom graders + optional LLM-as-judge | Aligns with §3 (code checks figures; judge scores interpretation) |
| Metrics DB | **SQLite** (or DuckDB) | Enough for run logs; portable |
| Auth | **None / local basic** for PoC | Not a multi-user product (§1) |
| Hosting | **Payloq on-prem / own servers** first; optional VPS for demo UI only | WO: company has servers for local models |
| Containerization | **Docker Compose** (app + Ollama) | Reproducible pilot setup |
| OSS license | Confirm with client (recommend **MIT** or **Apache-2.0**) | WO: “Everything is open source” |

**Not recommended for this PoC:** cloud-only LLM pipelines as primary path; production auth/billing; Finnish bank/accounting system connectors (real data is explicitly avoided).

---

## 6. Development needs from the client

| Item | Must-have | Can assume for MVP |
| --- | --- | --- |
| Approval of this plan + scope (A required; B required; §4 nice) | Yes | — |
| Target local hardware (GPU model/VRAM, or CPU-only constraint) | Yes | — |
| Preferred local runtime (Ollama vs vLLM vs other already on Payloq servers) | Yes | Default Ollama if unspecified |
| List of models to include (sizes + any finance-fine-tuned open models they care about) | Yes | 2–3 general local + 1 finance open model if named |
| Whether Finnish output is required for all scenarios or FI description + EN interpretation OK | Yes | Examples use `language: fi` descriptions |
| Open-source license choice | Yes | Implementation repo confirmed: [anmolwajid3/PayLoq](https://github.com/anmolwajid3/PayLoq) |
| Access to Payloq servers for model runs (SSH / VPN) **or** permission to use cloud GPU for *synthetic-only* runs | Yes | Local workstation if sufficient |
| Brand assets / marketing site | No | N/A for PoC |
| Domain / public hosting | No | Local demo |
| Real accounting/bank credentials, payment APIs | **No — out of scope** | Synthetic only |
| GDPR DPA / real personal data | **No** for this PoC | Synthetic fictional counterparties only; still avoid copying real names |
| Production auth (SSO, etc.) | No | Local |
| Cloud API keys (optional reference model) | Nice | Skip cloud baseline |
| Confirmation that example JSON schema may be evolved | Nice | WO already allows change |

---

## 7. Phased build plan

### Phase 0 — Align (approval gate)

- Freeze v0 schema (evolve from examples), VAT rules, validation rules, scenario list (3–5).
- **Done:** Written schema + acceptance checklist signed off.

### Phase 1 — MVP generator (Task A core)

- Parameter schema + hand-authored params for the 3 example scenarios reproduce (or closely match) attached datasets via code.
- Validators green on good / weak / cash_critical.
- JSON + Excel exporters with required tabs.
- CLI: `generate --input … --out …`
- **Done:** Regenerating from params yields valid, consistent packs; docs show how to add a fourth scenario.

### Phase 2 — LLM-assisted generation

- Prompt: NL description → parameters (structured JSON).
- LLM fills counterparties/descriptions; code still owns numbers.
- Ready-made scenario presets (3–5) callable by name.
- **Done:** “Cash critical in three weeks” style prompt produces a pack that validators accept and projection shows near-term negative cash when intended.

### Phase 3 — Benchmark (Task B)

- Model matrix runner (local).
- Graders: parameter correctness vs key; numeric reading / MoM change checks; interpretation rubric (factual, understandable, no invented causes).
- Metrics export (latency, tokens, hardware, rough cost).
- Optional LLM judge + human spot-check sheet.
- **Done:** Comparable scorecard across ≥2–3 local model sizes on fixed scenario set.

### Phase 4 — If time allows (§4)

- Chat demo over generated data with best model.
- Optional journal/accounting-entries dataset.
- Finer knobs for data volume/format.
- **Done:** Demo script + short evaluation note.

---

## 8. Risks / open questions

Ranked by impact on precision of build:

1. **Schema authority:** Examples are “illustration, not specification” and “may contain flaws.” Which fields are mandatory for acceptance vs free to redesign?
2. **Fidelity target:** Must generated packs numerically match the attached examples, or only match *behavior* (e.g. cash_critical goes negative ~week 3)?
3. **Accounting realism depth:** How Finnish GAAP / chart-of-accounts–faithful must P&L and BS be beyond the simplified line items in examples?
4. **Model shortlist & hardware:** Which exact open models and what GPU/CPU budget define “several sizes” and “finance-fine-tuned”?
5. **Finnish requirement bar:** Fail a model that cannot write FI interpretations, or score FI separately and allow EN-only finance models?
6. **Judge model:** Is a stronger *local* judge required, or is a cloud judge acceptable on synthetic outputs only?
7. **§4 priority:** Is chat demo more valuable than accounting entries if only one stretch goal fits?
8. **License & publication:** Public GitHub from day one vs private until pilot ends?
9. **“Invoices out of balance” scenario:** Mentioned in WO ready-made list but not in the zip—required for MVP scenario set?
10. **Projection policy:** Confirm overdue sales → week-1 inflow and exclusion of payroll/tax as permanent product rules vs example-only.

---

## 9. Repo / project layout

**Implementation repo (confirmed):** [https://github.com/anmolwajid3/PayLoq](https://github.com/anmolwajid3/PayLoq) — **greenfield** on this repository (scaffold the layout below into an empty/new tree; do not assume existing app code).

Suggested monorepo layout (Python-first):

```
PayLoq/                          # github.com/anmolwajid3/PayLoq
  README.md
  LICENSE
  pyproject.toml                 # uv workspace root
  packages/
    schemas/                     # Pydantic models, JSON Schema export
    generator/                   # params → monthly, cash, invoices, projection
    validate/                    # consistency checks + answer keys
    export_xlsx/                 # openpyxl writers
    llm/                         # local client adapters, prompts
    benchmark/                   # runners, graders, metrics
  apps/
    cli/                         # payloq generate | validate | bench
    demo_ui/                     # optional Streamlit/Gradio / later chat
  scenarios/                     # good, weak, cash_critical, …
    <name>/input.json
    <name>/expected/             # optional golden outputs
  runs/                          # gitignored benchmark artifacts
  tests/
  docker-compose.yml             # app + ollama
  docs/
    technical-plan.md            # this document (may live in project store until copied)
    schema.md
    evaluation.md
```

---

## Approval

Please confirm or amend:

1. Scope: Task A + Task B in MVP; §4 deferred unless time remains.  
2. Stack: Python + Pydantic + openpyxl + Ollama/vLLM + CLI-first.  
3. Answers to open questions **#1–5** (schema, fidelity, accounting depth, models/hardware, Finnish bar).  

After approval, implementation starts at Phase 0/1 without expanding into real-data product features.

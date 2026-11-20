# PayLoq schema (v0)

Schema is **free to evolve**. Figures are owned by code; the LLM only supplies parameters and descriptive text.

## Files per scenario pack

| File | Role |
| --- | --- |
| `input.json` | NL descriptions (FI+EN), options, structured parameters, optional `invoice_texts` |
| `monthly_reports.json` | 12–24 months of P&L + balance sheet |
| `cash_and_invoices.json` | 26-week balance history, open invoices, 8-week projection |
| `journal_entries.json` | Optional §4 synthetic journal / accounting entries (code-generated) |
| `scenario_<id>.xlsx` | Same data, bilingual FI/EN sheet labels (+ Journal entries sheet when present) |

## LLM-assisted fields (Phase 2)

`parameters_from_language_model` is validated with Pydantic (`ParametersFromLanguageModel`) after the adapter returns JSON. FR-A-11 clamps out-of-range values and **hard-repairs** `cost_shares_of_revenue` so the sum is ~0.9–1.0 (logged in `run_log.json` → `parameter_clips`).

| Field | Role | Notes |
| --- | --- | --- |
| `monthly_revenue_start_eur` | **Month-1** revenue (aliases: `revenue_monthly_start_eur`, `revenue_monthly_eur`) | Clipped 20k–10M; stated values must ground in the NL description |
| `monthly_revenue_growth` | MoM growth fraction (alias: `growth_per_month_fraction`; 0.003 = 0.3%) | −10% … +5% |
| `cost_shares_of_revenue` | materials/services/personnel/other | Each 0–1; **sum must be ~0.9–1.0**; unstated → industry×size assumed |
| `monthly_revenue_factors` | 12 floats Jan–Dec | Seasonality (e.g. winter 0.3, summer 1.0); applied to monthly revenue |
| `special_investment_eur` / `special_investment_month` | Capex / roof repair | 1-based month index (default 2); raises FA + cash outflow; clipped 0–10M |
| `one_off_events` | `[{type, amount_eur, month_index, direction, label}]` | CAPEX always outflow; missing month/direction rejected |
| `target_cash_at_end_eur` | Ending-cash target (alias: `covenant_min_cash_eur`) | Drives dynamics; clipped −50k–5M; last cash is **not** forced exact equality (see `run_log.ending_cash`) |
| `starting_cash_eur` | Opening cash | Required when LLM-extracted; unstated → hard error (not invented) |
| `days_sales_outstanding` / `days_payables_outstanding` | Payment terms (aliases: `dso_days` / `dpo_days`) | 14–90; unstated → industry×size assumed |
| `field_sources` | `stated` \| `assumed` per field | Provenance; Assumed values listed on Excel **Assumptions** tab |

**Work order D:** `projection_history_scale` is a **warning** (non-blocking); ratio is logged.

Optional `invoice_texts` (`InvoiceDescriptiveTexts`):

| Field | Role |
| --- | --- |
| `sales_counterparties` / `purchase_counterparties` | Fictional FI/EN names |
| `sales_descriptions` / `purchase_descriptions` | Invoice line labels |
| `language` | `fi` \| `en` |

Amounts, dates, VAT, and IDs remain generator-owned.

**Pack labelling:** ready-made presets keep `good` / `weak` / `cash_critical` / …. Custom `--from-text` packs use an industry-derived slug (e.g. `boutique_hotel`) so they are not mislabelled `scenario_cash_critical.xlsx`. Behaviour profile is recorded separately (`behavior_profile` in `run_log` / meta note).

## VAT

- Income statement lines: **VAT 0%**
- Receivables, payables, invoice amounts: **VAT 25.5%** (`VAT_RATE_FI`)

## Invariants (validators)

1. Each month: `total_assets == total_equity_and_liabilities`
2. Asset / liability line sums match totals
3. P&L lines reconcile (operating profit → net result)
4. Equity roll-forward (VR-04, **blocking**): `equity_t = equity_{t-1} + net_result_t` (− dividends/drawings if modeled)
5. Last month `cash` == last `balance_history.balance`
6. Σ open sales invoices == receivables; Σ open purchases == payables
7. Projection arithmetic: `balance += sales_inflow - purchase_outflow`
8. Behavioural (warnings): good stays solvent; weak loses money; cash_critical goes negative ~week 3

## Journal entries (§4 optional)

`journal_entries.json` is a simplified double-entry export derived from monthly P&L, special investment, and open invoices. Each voucher has balanced debit/credit lines on a synthetic chart of accounts (not an official Finnish tilikartta). See [phase8-stretch.md](phase8-stretch.md).

## Chat figures (§4)

Chat demo does **not** invent a new on-disk file. Code builds an in-memory figure summary (`build_chat_figures`) from the pack; stub/Ollama only interpret those numbers.

## Adding a scenario

1. Copy `scenarios/good/input.json` → `scenarios/<name>/input.json`
2. Set `options.scenario_id`, FI/EN descriptions, and parameters
3. Run `payloq generate --scenario <name> --out out/<name>`
4. Run `payloq validate out/<name>`

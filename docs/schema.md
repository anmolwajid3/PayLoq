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

`parameters_from_language_model` is validated with Pydantic (`ParametersFromLanguageModel`) after the adapter returns JSON.

Optional `invoice_texts` (`InvoiceDescriptiveTexts`):

| Field | Role |
| --- | --- |
| `sales_counterparties` / `purchase_counterparties` | Fictional FI/EN names |
| `sales_descriptions` / `purchase_descriptions` | Invoice line labels |
| `language` | `fi` \| `en` |

Amounts, dates, VAT, and IDs remain generator-owned.

## VAT

- Income statement lines: **VAT 0%**
- Receivables, payables, invoice amounts: **VAT 25.5%** (`VAT_RATE_FI`)

## Invariants (validators)

1. Each month: `total_assets == total_equity_and_liabilities`
2. Asset / liability line sums match totals
3. P&L lines reconcile (operating profit → net result)
4. Last month `cash` == last `balance_history.balance`
5. Σ open sales invoices == receivables; Σ open purchases == payables
6. Projection arithmetic: `balance += sales_inflow - purchase_outflow`
7. Behavioural (warnings): good stays solvent; weak loses money; cash_critical goes negative ~week 3

## Journal entries (§4 optional)

`journal_entries.json` is a simplified double-entry export derived from monthly P&L, special investment, and open invoices. Each voucher has balanced debit/credit lines on a synthetic chart of accounts (not an official Finnish tilikartta). See [phase8-stretch.md](phase8-stretch.md).

## Chat figures (§4)

Chat demo does **not** invent a new on-disk file. Code builds an in-memory figure summary (`build_chat_figures`) from the pack; stub/Ollama only interpret those numbers.

## Adding a scenario

1. Copy `scenarios/good/input.json` → `scenarios/<name>/input.json`
2. Set `options.scenario_id`, FI/EN descriptions, and parameters
3. Run `payloq generate --scenario <name> --out out/<name>`
4. Run `payloq validate out/<name>`

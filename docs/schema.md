# PayLoq schema (v0)

Schema is **free to evolve** in Phase 0/1. Figures are owned by code; the LLM only supplies parameters and descriptive text.

## Files per scenario pack

| File | Role |
| --- | --- |
| `input.json` | NL descriptions (FI+EN), options, structured parameters |
| `monthly_reports.json` | 12–24 months of P&L + balance sheet |
| `cash_and_invoices.json` | 26-week balance history, open invoices, 8-week projection |
| `scenario_<id>.xlsx` | Same data, bilingual FI/EN sheet labels |

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

## Adding a scenario

1. Copy `scenarios/good/input.json` → `scenarios/<name>/input.json`
2. Set `options.scenario_id`, FI/EN descriptions, and parameters
3. Run `payloq generate --scenario <name> --out out/<name>`
4. Run `payloq validate out/<name>`

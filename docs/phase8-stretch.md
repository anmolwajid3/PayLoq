# Phase 4 / §4 stretch — chat demo + journal entries

**Principle:** *Code calculates; the language model interprets.* Chat figures and journal lines are produced by Python. Stub and Ollama only phrase answers from those figures.

## Chat demo

Demo presets (FI + EN):

| Id | FI | EN |
| --- | --- | --- |
| `cash_drop` | Miksi kassa laski? | Why did cash drop? |
| `cash_negative` | Milloin kassa menee negatiiviseksi? | When does cash go negative? |

Code builds a figure pack (`balance_history_change`, `mom_cash_change`, `largest_weekly_cash_drops`, `first_negative_projection_week`, open-invoice sums, investment, …). The adapter (`stub` or `ollama`) calls `interpret_figures` only.

### CLI (Windows `cmd` one-liners)

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & uv sync & uv run payloq chat --scenario cash_critical --preset cash_negative --llm stub --language fi
```

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & uv run payloq generate --scenario weak --out out\weak & uv run payloq chat --pack out\weak --preset cash_drop --llm stub --show-figures
```

```bat
ollama pull llama3.2:1b & cd /d C:\Users\anmol\Desktop\PayLoq & uv run payloq chat --scenario cash_critical --question "When does cash go negative?" --llm ollama --language en
```

### API / UI

- `GET /api/chat/presets?language=fi|en`
- `POST /api/runs/{id}/chat` — body: `{ "preset": "cash_drop", "llm": "stub", "language": "fi" }` or `{ "question": "…" }`
- Run detail page: **Chat demo** panel (stub default; Ollama optional)

## Journal / accounting entries

Optional dataset `journal_entries.json` (+ Excel sheet **Journal entries**):

- Monthly P&L → simplified double-entry vouchers (revenue+VAT, purchases, personnel, other, depreciation, tax)
- Special investment parameter → fixed-asset / cash voucher
- Open invoices → AR/AP vouchers
- Synthetic chart of accounts (not official Finnish tilikartta); every entry balances debit = credit

### CLI

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & uv run payloq generate --scenario good --out out\good --journal
```

Disable with `--no-journal`. Default is **on**.

### API

- Generate endpoints accept `write_journal: true` (default)
- `POST /api/runs/{id}/journal` — build `journal_entries.json` for an older run

## Non-goals / coordination

- Does **not** change `benchmarks/matrix.example.json` or Phase 3 graders (scorecard worker owns bench config)
- Does **not** invent causes in chat answers beyond code figures
- Docker Compose app path unchanged (`docker compose up --build -d`)

# Ollama on Windows (Anmol’s Desktop)

PayLoq calls a **local** Ollama model to map Finnish/English NL → structured parameters, invoice descriptive texts, and benchmark interpretations. Generation and bench still work **without** Ollama via `--llm stub` / `--models stub`.

**Default / recommended CPU model:** `llama3.2:1b`  
**Optional larger pulls:** `llama3.2:3b`, `qwen2.5:3b` (see [`benchmarks/matrix.cpu.json`](../benchmarks/matrix.cpu.json))

Chat paste often strips newlines — use **one line** with ` & ` between commands.

## 1. Install Ollama

1. Download the Windows installer from [https://ollama.com/download](https://ollama.com/download)
2. Run the installer and finish the setup wizard
3. Confirm the tray app / service is running (`http://127.0.0.1:11434`)

```bat
ollama --version & powershell -Command "Invoke-RestMethod http://127.0.0.1:11434/api/tags"
```

## 2. Pull recommended (+ optional) models

Recommended only:

```bat
ollama pull llama3.2:1b & ollama list
```

Full CPU shortlist (recommended + optional):

```bat
ollama pull llama3.2:1b & ollama pull llama3.2:3b & ollama pull qwen2.5:3b & ollama list
```

## 3. Clone / update PayLoq on Desktop

```bat
cd /d C:\Users\anmol\Desktop & git clone https://github.com/anmolwajid3/PayLoq.git
```

If you already have the repo:

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & git fetch origin & git checkout main & git pull origin main
```

## 4. Install Python deps with uv

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & uv sync
```

## 5. Generate without LLM (presets)

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & uv run payloq generate --scenario cash_critical --out out\cash_critical & uv run payloq validate out\cash_critical
```

## 6. Generate from Finnish NL (stub — no Ollama)

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & uv run payloq generate --from-text "Pieni konepaja, kassa on kriittinen kolmen viikon päästä koska isot ostolaskut erääntyvät ennen myyntilaskuja." --llm stub --out out\from_text_stub & uv run payloq validate out\from_text_stub
```

## 7. Generate from Finnish NL (Ollama)

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & uv run payloq generate --from-text "Pieni konepaja, kassa on kriittinen kolmen viikon päästä koska isot ostolaskut erääntyvät ennen myyntilaskuja." --llm ollama --ollama-model llama3.2:1b --out out\from_text_ollama & uv run payloq validate out\from_text_ollama
```

If Ollama is down or the model is missing, PayLoq **falls back to the stub** by default. To fail hard:

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & uv run payloq generate --from-text "..." --llm ollama --no-fallback-stub --out out\from_text_ollama
```

## 8. Optional flags

| Flag | Meaning |
| --- | --- |
| `--from-text-file path.txt` | Read NL from a UTF-8 file |
| `--language fi` | Primary language (default `fi`) |
| `--industry "..."` | Industry hint for the prompt |
| `--months 12` | History length 12–24 |
| `--ollama-host http://127.0.0.1:11434` | Custom Ollama URL |
| `--llm stub` | Keyword heuristic + built-in FI/EN invoice texts |

## 9. Benchmark / Ollama scorecard

Stub only (always works):

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & uv sync & uv run payloq bench --models stub --out runs\benchmark
```

Recommended live cell (skips Ollama models if daemon is down):

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & ollama pull llama3.2:1b & uv run payloq bench --models shortlist:recommended --out runs\benchmark_rec
```

Full CPU shortlist matrix:

```bat
cd /d C:\Users\anmol\Desktop\PayLoq & ollama pull llama3.2:1b & ollama pull llama3.2:3b & ollama pull qwen2.5:3b & uv run payloq bench --config benchmarks\matrix.cpu.json --out runs\benchmark_cpu
```

Artifacts under `runs\…`: `results.json`, `scorecard.json`, `scorecard.csv`, `runs.csv`, `metrics.sqlite`, `spotcheck.csv`. See [evaluation.md](evaluation.md) for FI quality bands.

## Principle reminder

Code owns **all numbers**. The LLM only supplies parameters and descriptive texts (counterparties / invoice lines), and interprets ready-made figures in the benchmark.

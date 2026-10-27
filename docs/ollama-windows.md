# Ollama on Windows (Anmol’s Desktop)

PayLoq Phase 2 can call a **local** Ollama model to map Finnish/English NL → structured parameters and invoice descriptive texts. Generation still works **without** Ollama via `--llm stub` (default).

**Default model (CPU-friendly):** `llama3.2:1b`

## 1. Install Ollama

1. Download the Windows installer from [https://ollama.com/download](https://ollama.com/download)
2. Run the installer and finish the setup wizard
3. Confirm the tray app / service is running (Ollama listens on `http://127.0.0.1:11434`)

PowerShell check:

```powershell
ollama --version
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

## 2. Pull the default small model

```powershell
ollama pull llama3.2:1b
```

List local models:

```powershell
ollama list
```

## 3. Clone / update PayLoq on Desktop

```powershell
cd C:\Users\anmol\Desktop
git clone https://github.com/anmolwajid3/PayLoq.git
cd C:\Users\anmol\Desktop\PayLoq
```

If you already have the repo:

```powershell
cd C:\Users\anmol\Desktop\PayLoq
git fetch origin
git checkout <phase2-branch-or-main>
git pull
```

## 4. Install Python deps with uv

```powershell
cd C:\Users\anmol\Desktop\PayLoq
uv sync
```

## 5. Generate without LLM (presets — same as Phase 1)

```powershell
cd C:\Users\anmol\Desktop\PayLoq
uv run payloq generate --scenario cash_critical --out out\cash_critical
uv run payloq validate out\cash_critical
```

## 6. Generate from Finnish NL text (stub — no Ollama)

```powershell
cd C:\Users\anmol\Desktop\PayLoq
uv run payloq generate --from-text "Pieni konepaja, kassa on kriittinen kolmen viikon päästä koska isot ostolaskut erääntyvät ennen myyntilaskuja." --llm stub --out out\from_text_stub
uv run payloq validate out\from_text_stub
```

## 7. Generate from Finnish NL text (Ollama)

```powershell
cd C:\Users\anmol\Desktop\PayLoq
uv run payloq generate --from-text "Pieni konepaja, kassa on kriittinen kolmen viikon päästä koska isot ostolaskut erääntyvät ennen myyntilaskuja." --llm ollama --ollama-model llama3.2:1b --out out\from_text_ollama
uv run payloq validate out\from_text_ollama
```

If Ollama is down or the model is missing, PayLoq **falls back to the stub** by default and prints a warning. To fail hard instead:

```powershell
uv run payloq generate --from-text "..." --llm ollama --no-fallback-stub --out out\from_text_ollama
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

## Principle reminder

Code owns **all numbers**. The LLM only supplies parameters and descriptive texts (counterparties / invoice lines).

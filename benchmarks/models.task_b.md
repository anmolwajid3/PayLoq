# Task B model catalog

Fair compare: same seed (`42`), same scenario descriptions, same prompts. Code calculates; models extract/interpret only. Finnish: score **FI band separately** — many finance models are EN-primary.

Verify tags still exist and check licenses on [Ollama](https://ollama.com/library) / Hugging Face before pulling.

## 1. General-purpose (Ollama library — verified tags)

| Model | Ollama tag | ~size | Status |
| --- | --- | --- | --- |
| Qwen2.5 0.5B | `qwen2.5:0.5b` | 0.5B | In matrix |
| Qwen2.5 3B | `qwen2.5:3b` | 3B | In matrix (already tested) |
| Qwen2.5 7B | `qwen2.5:7b` | 7B | Default pack / judge (already tested) |
| Llama 3.2 1B | `llama3.2:1b` | 1B | In matrix (already tested) |
| Llama 3.2 3B | `llama3.2:3b` | 3B | In matrix (already tested) |
| Llama 3.1 8B | `llama3.1:8b` | 8B | In matrix — size step-up |
| Mistral 7B | `mistral:7b` | 7B | In matrix — other architecture |
| Phi-3 mini | `phi3:mini` | 3.8B | In matrix |
| Gemma 2 2B | `gemma2:2b` | 2B | In matrix |
| Gemma 2 9B | `gemma2:9b` | 9B | In matrix (heavy on Mac CPU) |

## 2. Finance-fine-tuned (open)

| Model | Runnable tag / path | Status |
| --- | --- | --- |
| Nexus Finance (Qwen2.5-1.5B) | `FableForge-AI/nexus-finance:q4_k_m` | In matrix — already scorecarded |
| FinGPT-MT Llama-3 8B LoRA | `hf.co/gaianet/FinGPT-MT-Llama-3-8B-LoRA-GGUF:Q4_K_M` | In matrix — verify HF license; expect schema-format friction |
| FinMA-7B (PIXIU / TheFinAI) | HF only | Catalog excluded until custom GGUF/Modelfile |
| Instruct-FinGPT / FinLLaMA | HF / LoRA | Catalog excluded until pinned GGUF |
| FinTral | — | **Excluded** — weights not public |
| FinBERT | — | **Excluded** from generative Task B (classification only) |

Finance models are often ~7–8B LLaMA-class — size alone is a weak reason to prefer them over `qwen2.5:7b` / `llama3.1:8b`. Test JSON/schema extract before trusting param scores.

## 3. Cloud reference (synthetic data only)

| Model | Status |
| --- | --- |
| Current Claude via API | **Not wired** — no cloud adapter yet. When added: synthetic scenarios only; behind an explicit env flag. |

## Configs

| File | Use |
| --- | --- |
| `benchmarks/matrix.cpu.json` | Mac-friendly default shortlist (qwen + llama + nexus) |
| `benchmarks/matrix.task_b.json` | Full Task B matrix above (`skip_unavailable: true`) |

```bash
cd ~/Desktop/PayLoq
git checkout main
git pull origin main
export PAYLOQ_OLLAMA_TIMEOUT=600
uv run payloq bench --config benchmarks/matrix.task_b.json --out runs/benchmark_task_b_full --judge
```

Pull only what you need; unpulled cells are skipped.

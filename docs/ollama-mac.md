# Ollama on Mac (Docker Compose)

Primary path: `~/Desktop/PayLoq`. The web **Generate** page lists whatever models Ollama reports via `/api/tags` — there is **no Stub** option in the UI.

## Start stack + pull small CPU models

```bash
cd ~/Desktop/PayLoq
git fetch --prune && git checkout main && git pull origin main
docker compose --profile ollama up --build -d
docker compose --profile ollama exec ollama ollama pull llama3.2:1b
docker compose --profile ollama exec ollama ollama pull qwen2.5:0.5b
docker compose --profile ollama exec ollama ollama pull llama3.2:3b
docker compose --profile ollama exec ollama ollama list
```

Open http://localhost:5173 · `payloq` / `payloq`.

## Checkout a PR with `gh`

```bash
cd ~/Desktop/PayLoq
gh pr checkout <PR_NUMBER>
docker compose --profile ollama up --build -d
```

## After merge — sync main

```bash
cd ~/Desktop/PayLoq
git fetch --prune
git checkout main
git pull origin main
git branch -d cursor/<merged-branch>   # optional
```

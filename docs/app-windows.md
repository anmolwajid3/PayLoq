# PayLoq app layer — Windows (Anmol)

**Target folder:** `C:\Users\anmol\Desktop\PayLoq`  
**UI:** http://localhost:5173  
**API:** http://localhost:8000/api/health  
**Login:** `payloq` / `payloq`

Prefer **Docker Desktop + Compose** (Postgres). If Compose is too heavy, use the **SQLite** path below.

---

## A. Docker Desktop path (default)

### 1. Install Docker Desktop (one-time)

Open a browser and install Docker Desktop for Windows:

https://www.docker.com/products/docker-desktop/

Start Docker Desktop and wait until it says Docker is running.

### 2. Get / update the repo

```powershell
cd C:\Users\anmol\Desktop\PayLoq

git fetch origin

git checkout main

git pull origin main
```

### 3. Start Postgres + API + web

```powershell
cd C:\Users\anmol\Desktop\PayLoq

docker compose up --build -d
```

Wait until containers are healthy (about a minute the first time).

### 4. Check API health

```powershell
curl http://localhost:8000/api/health
```

Or open http://localhost:8000/docs in a browser.

### 5. Open the UI

Open:

http://localhost:5173

Sign in with:

- Username: `payloq`
- Password: `payloq`

### 6. Stop the stack

```powershell
cd C:\Users\anmol\Desktop\PayLoq

docker compose down
```

Optional Ollama profile:

```powershell
cd C:\Users\anmol\Desktop\PayLoq

docker compose --profile ollama up --build -d
```

---

## B. SQLite path (no Docker DB)

Requires **Python 3.12+**, [uv](https://docs.astral.sh/uv/), and **Node.js 20+**.

### 1. Install deps

```powershell
cd C:\Users\anmol\Desktop\PayLoq

uv sync
```

```powershell
cd C:\Users\anmol\Desktop\PayLoq\apps\web

npm install
```

### 2. Start API (SQLite + auto-seed)

```powershell
cd C:\Users\anmol\Desktop\PayLoq

mkdir data -ErrorAction SilentlyContinue

$env:PAYLOQ_DATABASE_URL = "sqlite:///./data/payloq.db"

$env:PAYLOQ_ARTIFACT_DIR = "./data/artifacts"

uv run uvicorn payloq_api.main:app --host 127.0.0.1 --port 8000
```

Leave that window open.

### 3. Start web (new PowerShell window)

```powershell
cd C:\Users\anmol\Desktop\PayLoq\apps\web

npm run dev
```

Open http://localhost:5173 and log in as `payloq` / `payloq`.

### 4. Optional Alembic migrate (Postgres or SQLite)

```powershell
cd C:\Users\anmol\Desktop\PayLoq\apps\api

$env:PAYLOQ_DATABASE_URL = "sqlite:///../../data/payloq.db"

uv run --directory ../.. alembic -c alembic.ini upgrade head
```

For Docker Postgres from the host:

```powershell
cd C:\Users\anmol\Desktop\PayLoq\apps\api

$env:PAYLOQ_DATABASE_URL = "postgresql+psycopg://payloq:payloq@localhost:5432/payloq"

uv run --directory ../.. alembic -c alembic.ini upgrade head
```

(The API also calls `create_all` + seed on startup for PoC convenience.)

---

## What to try in the UI

1. **Scenarios** — open `good` / `weak` / `cash_critical`, generate a pack.
2. **Generate** — paste Finnish NL text, choose stub (or Ollama), run.
3. **Runs** — view validation, cash history + projection charts, download JSON/Excel.

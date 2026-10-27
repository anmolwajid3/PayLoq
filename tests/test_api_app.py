"""API layer smoke tests (SQLite in-memory / temp file)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Configure env before importing the app
_tmp = Path(__file__).resolve().parent / "_api_test_data"
_tmp.mkdir(exist_ok=True)
os.environ["PAYLOQ_DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["PAYLOQ_ARTIFACT_DIR"] = str(_tmp / "artifacts")
os.environ["PAYLOQ_JWT_SECRET"] = "test-secret"
os.environ["PAYLOQ_AUTH_USERNAME"] = "payloq"
os.environ["PAYLOQ_AUTH_PASSWORD"] = "payloq"

from payloq_api.config import get_settings

get_settings.cache_clear()

from fastapi.testclient import TestClient
from payloq_api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "sqlite"


def test_login_and_scenarios(client: TestClient):
    bad = client.post("/api/auth/login", json={"username": "x", "password": "y"})
    assert bad.status_code == 401

    login = client.post("/api/auth/login", json={"username": "payloq", "password": "payloq"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == "payloq"

    scenarios = client.get("/api/scenarios", headers=headers)
    assert scenarios.status_code == 200
    slugs = {s["slug"] for s in scenarios.json()}
    assert {"good", "weak", "cash_critical"} <= slugs


def test_generate_preset_cash_critical(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "payloq", "password": "payloq"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    run = client.post(
        "/api/generate/preset",
        headers=headers,
        json={"scenario_slug": "cash_critical", "seed": 42, "write_xlsx": True},
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "ok"
    assert body["validation_ok"] is True
    assert body["pack_summary"]["balance_history"]
    assert body["pack_summary"]["projection"]
    assert "input.json" in body["artifacts"]
    assert any(a.endswith(".xlsx") for a in body["artifacts"])

    detail = client.get(f"/api/runs/{body['id']}", headers=headers)
    assert detail.status_code == 200

    art = client.get(
        f"/api/runs/{body['id']}/artifacts/cash_and_invoices.json",
        headers=headers,
    )
    assert art.status_code == 200
    assert "balance_history" in art.json()


def test_generate_from_text_stub(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "payloq", "password": "payloq"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    run = client.post(
        "/api/generate/from-text",
        headers=headers,
        json={
            "text": "Pieni konepaja, kassa on kriittinen kolmen viikon päästä.",
            "llm": "stub",
            "language": "fi",
            "months": 12,
        },
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "ok"
    assert body["validation_ok"] is True
    assert body["source"] == "from_text"
    assert body["llm_adapter"] == "stub"
    assert "journal_entries.json" in body["artifacts"]


def test_chat_demo_on_run(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "payloq", "password": "payloq"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    presets = client.get("/api/chat/presets?language=fi", headers=headers)
    assert presets.status_code == 200
    ids = {p["id"] for p in presets.json()}
    assert {"cash_drop", "cash_negative"} <= ids

    run = client.post(
        "/api/generate/preset",
        headers=headers,
        json={"scenario_slug": "cash_critical", "seed": 42, "write_xlsx": False},
    )
    assert run.status_code == 200, run.text
    run_id = run.json()["id"]

    chat = client.post(
        f"/api/runs/{run_id}/chat",
        headers=headers,
        json={"preset": "cash_negative", "language": "fi", "llm": "stub"},
    )
    assert chat.status_code == 200, chat.text
    payload = chat.json()
    assert payload["preset"] == "cash_negative"
    assert payload["figures"]["first_negative_projection_week"] is not None
    assert payload["answer"]

    drop = client.post(
        f"/api/runs/{run_id}/chat",
        headers=headers,
        json={"preset": "cash_drop", "language": "en", "llm": "stub"},
    )
    assert drop.status_code == 200, drop.text
    assert drop.json()["question"] == "Why did cash drop?"

"""API layer smoke tests (SQLite in-memory / temp file)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

# Configure env before importing the app
_tmp = Path(__file__).resolve().parent / "_api_test_data"
if _tmp.exists():
    shutil.rmtree(_tmp)
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


def test_llm_models_endpoint(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "payloq", "password": "payloq"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    res = client.get("/api/llm/models", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "available" in body
    assert "models" in body
    assert isinstance(body["models"], list)
    assert "qwen2.5:7b" in body["recommended"]
    # UI must never need stub here — recommended tags are Ollama-only.
    assert all("stub" not in t for t in body["recommended"])
    assert "compare_shortlist" in body
    assert "qwen2.5:3b" in body["compare_shortlist"]
    assert all("stub" not in t for t in body["compare_shortlist"])


def test_generate_from_text_rejects_stub(client: TestClient):
    """From-text is Ollama-only — stub keyword must be rejected at the schema."""
    login = client.post("/api/auth/login", json={"username": "payloq", "password": "payloq"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    run = client.post(
        "/api/generate/from-text",
        headers=headers,
        json={
            "text": "Pieni konepaja, kassa on kriittinen kolmen viikon päästä.",
            "llm": "stub",
            "language": "fi",
            "industry": "machine shop",
            "company_size": "8",
            "months": 12,
            "seed": 42,
        },
    )
    assert run.status_code == 422, run.text
    detail = str(run.json())
    assert "ollama" in detail.lower()


def test_generate_from_text_background_returns_running(client: TestClient, monkeypatch):
    """background=true returns immediately with progress; worker is scheduled."""
    called: list[int] = []

    def fake_job(run_id: int, **_kwargs):
        called.append(run_id)

    monkeypatch.setattr(
        "payloq_api.routers.runs.execute_from_text_job", fake_job
    )

    login = client.post("/api/auth/login", json={"username": "payloq", "password": "payloq"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.post(
        "/api/generate/from-text",
        headers=headers,
        json={
            "text": "Monthly revenue 250000 euro. Starting cash 150000.",
            "llm": "ollama",
            "language": "en",
            "industry": "retail",
            "company_size": "12",
            "months": 12,
            "seed": 1,
            "background": True,
            "compare": False,
            "ollama_model": "qwen2.5:7b",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "running"
    assert body["progress"] is not None
    assert body["progress"]["stage"] == "queued"
    assert called == [body["id"]]

    again = client.get(f"/api/runs/{body['id']}", headers=headers)
    assert again.status_code == 200
    assert again.json()["progress"]["percent"] >= 0


def test_generate_from_text_accepts_large_company_size():
    """Request schema normalizes Large → large (generation itself needs Ollama)."""
    from payloq_api.schemas import GenerateFromTextRequest

    body = GenerateFromTextRequest(
        text="Mid-market steel plant; cash is tight within three weeks.",
        llm="ollama",
        language="en",
        industry="steel",
        company_size="Large",
        months=12,
        seed=7,
    )
    assert body.company_size == "large"


def test_generate_from_text_rejects_bad_company_size(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "payloq", "password": "payloq"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    empty = client.post(
        "/api/generate/from-text",
        headers=headers,
        json={
            "text": "Pieni konepaja.",
            "llm": "ollama",
            "company_size": "  ",
            "months": 12,
        },
    )
    assert empty.status_code == 422

    bad = client.post(
        "/api/generate/from-text",
        headers=headers,
        json={
            "text": "Pieni konepaja.",
            "llm": "ollama",
            "company_size": "huge",
            "months": 12,
        },
    )
    assert bad.status_code == 422
    detail = str(bad.json())
    assert "large" in detail.lower() or "employees" in detail.lower()


def test_chat_uses_run_model_without_llm_body(client: TestClient):
    """UI chat omits llm — endpoint must reuse the run's stored adapter/model."""
    login = client.post("/api/auth/login", json={"username": "payloq", "password": "payloq"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Preset run (no from-text stub). Chat may still use stub override / defaults.
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
        json={"preset": "cash_drop", "language": "fi", "llm": "stub"},
    )
    assert chat.status_code == 200, chat.text
    payload = chat.json()
    assert payload["preset"] == "cash_drop"
    assert payload["answer"]
    assert payload["llm_adapter"] in {"stub", "ollama", "ollama->stub"}


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

    # Explicit stub override for CI (preset runs have llm_adapter=none).
    chat = client.post(
        f"/api/runs/{run_id}/chat",
        headers=headers,
        json={"preset": "cash_negative", "language": "fi", "llm": "stub"},
    )
    assert chat.status_code == 200, chat.text
    payload = chat.json()
    assert payload["preset"] == "cash_negative"
    assert payload["figures"]["first_negative_projection_week"] is not None
    assert payload["figures"]["first_negative_date"] is not None
    assert payload["figures"]["first_negative_balance"] is not None
    assert payload["answer"]
    assert payload["figures"]["first_negative_date"] in payload["answer"]
    assert "when the balance history change is negative" not in payload["answer"].lower()

    drop = client.post(
        f"/api/runs/{run_id}/chat",
        headers=headers,
        json={"preset": "cash_drop", "language": "en", "llm": "stub"},
    )
    assert drop.status_code == 200, drop.text
    assert drop.json()["question"] == "Why did cash drop?"

    empty_sugs = client.post(
        f"/api/runs/{run_id}/chat/suggestions",
        headers=headers,
        json={"language": "fi", "prior_questions": []},
    )
    assert empty_sugs.status_code == 200, empty_sugs.text
    empty_ids = [row["id"] for row in empty_sugs.json()]
    assert empty_ids[:2] == ["cash_drop", "cash_negative"]

    refreshed = client.post(
        f"/api/runs/{run_id}/chat/suggestions",
        headers=headers,
        json={
            "language": "en",
            "prior_questions": [
                "Why did cash drop?",
                "When does cash go negative?",
            ],
        },
    )
    assert refreshed.status_code == 200, refreshed.text
    refreshed_ids = {row["id"] for row in refreshed.json()}
    assert "cash_drop" not in refreshed_ids
    assert "cash_negative" not in refreshed_ids
    assert refreshed.json(), "expected dynamic follow-ups from run figures"

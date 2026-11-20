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
    assert "llama3.2:1b" in body["recommended"]
    # UI must never need stub here — recommended tags are Ollama-only.
    assert all("stub" not in t for t in body["recommended"])


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
            "industry": "machine shop",
            "company_size": "8",
            "months": 12,
            "seed": 42,
        },
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "ok"
    assert body["validation_ok"] is True
    assert body["source"] == "from_text"
    assert body["llm_adapter"] == "stub"
    assert body["seed"] == 42
    assert body.get("llm_model") in (None, "")
    assert "journal_entries.json" not in body.get("artifacts", [])
    soft = (body.get("pack_summary") or {}).get("nl_soft_warnings") or []
    assert isinstance(soft, list)
    # Stub heuristics + critical NL should surface at least the stub soft-hint.
    assert any(w.get("code") == "nl_stub_heuristic" for w in soft)
    assert (body.get("pack_summary") or {}).get("parameters")
    assert (body.get("pack_summary") or {}).get("language") == "fi"
    options = (body.get("pack_summary") or {}).get("options") or {}
    assert options.get("company_size") == "8 employees"
    assert options.get("industry") == "machine shop"
    assert options.get("months") == 12

    art = client.get(
        f"/api/runs/{body['id']}/artifacts/input.json",
        headers=headers,
    )
    assert art.status_code == 200
    assert art.json()["options"]["company_size"] == "8 employees"

    log = client.get(
        f"/api/runs/{body['id']}/artifacts/run_log.json",
        headers=headers,
    )
    assert log.status_code == 200
    run_log = log.json()
    assert run_log["seed"] == 42
    assert run_log["options"]["company_size"] == "8 employees"


def test_generate_from_text_accepts_large_company_size(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "payloq", "password": "payloq"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    run = client.post(
        "/api/generate/from-text",
        headers=headers,
        json={
            "text": "Mid-market steel plant; cash is tight within three weeks.",
            "llm": "stub",
            "language": "en",
            "industry": "steel",
            "company_size": "Large",
            "months": 12,
            "seed": 7,
        },
    )
    assert run.status_code == 200, run.text
    body = run.json()
    options = (body.get("pack_summary") or {}).get("options") or {}
    assert options.get("company_size") == "large"
    params = (body.get("pack_summary") or {}).get("parameters") or {}
    assert params.get("monthly_revenue_start_eur") == 1_200_000.0


def test_generate_from_text_rejects_bad_company_size(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "payloq", "password": "payloq"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    empty = client.post(
        "/api/generate/from-text",
        headers=headers,
        json={
            "text": "Pieni konepaja.",
            "llm": "stub",
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
            "llm": "stub",
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
    run_id = run.json()["id"]
    assert run.json()["llm_adapter"] == "stub"

    chat = client.post(
        f"/api/runs/{run_id}/chat",
        headers=headers,
        json={"preset": "cash_drop", "language": "fi"},
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

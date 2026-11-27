"""Pengamanan API (api/security.py) dan konfigurasi embedding lewat .env."""

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from api import security
from pipeline import config, knowledge


@pytest.fixture
def client(monkeypatch):
    """Aplikasi mini dengan dependency yang sama seperti /api di api/main.py."""
    monkeypatch.setattr(security, "_api_window", security.SlidingWindow())
    monkeypatch.setattr(security, "_chat_window", security.SlidingWindow())
    monkeypatch.setattr(config.settings, "api_key", "kunci-rahasia")
    monkeypatch.setattr(config.settings, "api_rate_per_min", 3)
    monkeypatch.setattr(config.settings, "agent_rate_per_min", 1)
    router = APIRouter(prefix="/api", dependencies=[Depends(security.rate_limit)])
    router.get("/data")(lambda: {"ok": True})
    router.post("/chat", dependencies=[Depends(security.chat_rate_limit)])(lambda: {"ok": True})
    router.post("/admin/x", dependencies=[Depends(security.require_admin)])(lambda: {"ok": True})
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_public_endpoint_rate_limited_per_ip_but_key_is_exempt(client):
    assert [client.get("/api/data").status_code for _ in range(4)] == [200, 200, 200, 429]
    assert client.get("/api/data", headers={"X-API-Key": "kunci-rahasia"}).status_code == 200
    assert client.get("/api/data", headers={"X-API-Key": "salah"}).status_code == 429
    assert client.get("/api/data", headers={"X-Real-IP": "10.0.0.2"}).status_code == 200  # IP lain, jatah sendiri


def test_chat_has_its_own_tighter_limit(client):
    assert [client.post("/api/chat").status_code for _ in range(2)] == [200, 429]


def test_admin_requires_key(client, monkeypatch):
    assert client.post("/api/admin/x").status_code == 401
    assert client.post("/api/admin/x", headers={"X-API-Key": "salah"}).status_code == 401
    assert client.post("/api/admin/x", headers={"X-API-Key": "kunci-rahasia"}).status_code == 200
    monkeypatch.setattr(config.settings, "api_key", None)
    assert client.post("/api/admin/x", headers={"X-API-Key": "apa saja"}).status_code == 503


def test_openapi_documents_api_key_for_authorize_button():
    from api.main import app
    schemes = app.openapi()["components"]["securitySchemes"]
    assert schemes["APIKeyHeader"]["name"] == "X-API-Key"


def test_chat_daily_limit_switches_to_saving_mode(monkeypatch):
    from api import main
    from api.agent import core, fallback
    monkeypatch.setattr(main.settings, "gemini_api_key", "x")
    monkeypatch.setattr(main.settings, "agent_daily_limit", 5)
    monkeypatch.setattr(main, "_agent_daily_used", lambda: 5)
    monkeypatch.setattr(main, "_log_agent", lambda *a, **k: None)
    monkeypatch.setattr(main, "_answer_cache", {})
    monkeypatch.setattr(security, "_chat_window", security.SlidingWindow())
    monkeypatch.setattr(core, "run", lambda *a, **k: pytest.fail("LLM tidak boleh dipanggil"))
    monkeypatch.setattr(fallback, "answer",
                        lambda q, reason="quota": core.AgentResult(answer=f"hemat:{reason}", status="fallback"))
    r = TestClient(main.app).post("/api/chat", json={"message": "Jakarta hujan?"})
    assert r.status_code == 200 and r.json()["answer"] == "hemat:limit"


def test_embed_prefix_auto_for_e5_and_overridable(monkeypatch):
    s = config.settings
    monkeypatch.setattr(s, "embed_query_prefix", None)
    monkeypatch.setattr(s, "embed_doc_prefix", None)
    monkeypatch.setattr(s, "embed_model", "intfloat/multilingual-e5-small")
    assert (knowledge.embed_prefix("query"), knowledge.embed_prefix("document")) == ("query: ", "passage: ")
    monkeypatch.setattr(s, "embed_model", "BAAI/bge-m3")
    assert knowledge.embed_prefix("query") == ""
    monkeypatch.setattr(s, "embed_query_prefix", "cari: ")
    assert knowledge.embed_prefix("query") == "cari: "


def test_embed_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("EMBED_MODEL", "BAAI/bge-m3")
    monkeypatch.setenv("EMBED_DIM", "1024")
    s = config.Settings()
    assert (s.embed_model, s.embed_dim) == ("BAAI/bge-m3", 1024)

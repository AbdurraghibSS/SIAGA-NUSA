"""Normalisasi URL database untuk Supabase/Vercel."""

from pipeline.config import Settings


def test_supabase_url_gets_psycopg_driver_and_pooler_detection():
    s = Settings(database_url="postgresql://postgres.abc:pw@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres")
    assert s.database_url.startswith("postgresql+psycopg://") and s.db_transaction_pooler
    s = Settings(database_url="postgres://u:pw@host:5432/db")
    assert s.database_url.startswith("postgresql+psycopg://") and not s.db_transaction_pooler
    assert Settings(database_url="postgresql+psycopg://u:p@localhost:5434/x").database_url.endswith("5434/x")


def test_basic_auth_middleware_when_password_set(monkeypatch):
    import importlib

    import api.main
    from pipeline import config
    monkeypatch.setattr(config.settings, "basic_auth_user", "tim")
    monkeypatch.setattr(config.settings, "basic_auth_password", "rahasia")
    monkeypatch.setattr(config.settings, "serve_web", False)
    m = importlib.reload(api.main)
    from fastapi.testclient import TestClient
    c = TestClient(m.app)
    assert c.get("/api/cities").status_code == 401
    assert c.get("/api/cities", auth=("tim", "salah")).status_code == 401
    assert c.get("/openapi.json", auth=("tim", "rahasia")).status_code == 200
    # Klien program (Postman/skrip) boleh lolos dengan X-API-Key tanpa login Basic.
    monkeypatch.setattr(config.settings, "api_key", "kunci")
    assert c.get("/openapi.json", headers={"X-API-Key": "kunci"}).status_code == 200
    assert c.get("/openapi.json", headers={"X-API-Key": "salah"}).status_code == 401
    monkeypatch.setattr(config.settings, "basic_auth_password", None)
    importlib.reload(api.main)

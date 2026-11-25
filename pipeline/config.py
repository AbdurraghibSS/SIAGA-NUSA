"""Konfigurasi dari environment / `.env` · settings from the environment.

Pola dari sesi 9 & 11: satu kelas `BaseSettings`, nilai rahasia tidak pernah
ditulis di kode. Salin `.env.example` menjadi `.env` lalu sesuaikan.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://siaga:siaga_dev@localhost:5434/siaga_nusa"

    # Snapshot prakiraan dikumpulkan GitHub Actions ke branch ini (BMKG tidak punya arsip).
    snapshot_remote: str = "origin"
    snapshot_branch: str = "data-snapshots"
    data_dir: Path = REPO_ROOT / "data"

    # MLflow (plan §6.5): satu server tracking untuk semua eksperimen, artefak disimpan
    # oleh server (--serve-artifacts). Di laptop pengembangan server ini sudah jalan di :5000.
    mlflow_tracking_uri: str = "http://127.0.0.1:5000"

    # True: API juga menyajikan dasbor web/ (uvicorn langsung). Di Docker, dasbor disajikan
    # container frontend (nginx), jadi backend memakai SERVE_WEB=false.
    serve_web: bool = True

    # Kunci untuk endpoint admin API (mis. menjalankan ulang pipeline). Kosong = endpoint dimatikan.
    api_key: str | None = None

    # Agen Tanya (plan §7): Gemini dengan function calling. Kunci kosong = agen dimatikan
    # (endpoint /api/chat menjawab 503, dasbor tetap jalan).
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    # Dipakai berurutan kalau model utama kena 429 (kuota gratis habis). Dipisah koma.
    gemini_fallback_models: str = "gemini-3.5-flash-lite"
    agent_cache_ttl_s: int = 600       # pertanyaan sama (tanpa riwayat) dijawab dari cache selama 10 menit
    agent_max_rounds: int = 5          # maksimal putaran function calling per pertanyaan
    agent_timeout_s: float = 30.0      # batas total satu pertanyaan
    agent_rate_per_min: int = 10       # pertanyaan per menit per alamat IP

    # RAG: PDF panduan kesiapsiagaan (tidak di-commit, taruh di docs/) → vector DB Qdrant.
    knowledge_dir: Path = REPO_ROOT / "docs"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "siaganusa-panduan"
    embed_model: str = "intfloat/multilingual-e5-small"  # lokal, lihat pipeline/knowledge.py

    # env_ignore_empty: baris kosong di .env (mis. "GEMINI_MODEL=") tidak menimpa default.
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", case_sensitive=False, extra="ignore",
                                      env_ignore_empty=True)

    @property
    def snapshot_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"


settings = Settings()

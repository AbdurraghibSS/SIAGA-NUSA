"""Konfigurasi dari environment / `.env` · settings from the environment.

Pola dari sesi 9 & 11: satu kelas `BaseSettings`, nilai rahasia tidak pernah
ditulis di kode. Salin `.env.example` menjadi `.env` lalu sesuaikan.
"""

import os
from pathlib import Path

from pydantic import field_validator
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

    # Kunci header X-API-Key (api/security.py): wajib untuk endpoint admin (kosong = admin dimatikan),
    # opsional di endpoint lain untuk klien tepercaya (bebas batas request per IP).
    api_key: str | None = None
    api_rate_per_min: int = 120        # request /api/* per menit per IP (dasbor memuat ±10 sekaligus)

    # Login sederhana untuk deploy publik tanpa nginx (Vercel). Kosong = terbuka.
    basic_auth_user: str = "tim"
    basic_auth_password: str | None = None

    # Agen Tanya (plan §7): Gemini dengan function calling. Kunci kosong = agen dimatikan
    # (endpoint /api/chat menjawab 503, dasbor tetap jalan).
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    # Dipakai berurutan kalau model utama kena 429 (kuota gratis habis). Dipisah koma.
    # Tiap model punya kapasitas sendiri: saat 3.8 kena 503 (25 Nov 2026), 3.6 dan 3.5-lite tetap jalan.
    gemini_fallback_models: str = "gemini-3.6-flash,gemini-3.5-flash-lite"
    agent_cache_ttl_s: int = 600       # pertanyaan sama (tanpa riwayat) dijawab dari cache selama 10 menit
    agent_max_rounds: int = 5          # maksimal putaran function calling per pertanyaan
    agent_timeout_s: float = 30.0      # batas total satu pertanyaan
    gemini_call_timeout_s: float = 12.0  # per panggilan; model lambat/504 cepat dilepas ke model cadangan
    agent_rate_per_min: int = 10       # pertanyaan per menit per alamat IP
    # Batas global pertanyaan yang memakai LLM per 24 jam (semua pengguna, dihitung dari agent_logs).
    # Lewat batas → mode hemat tanpa LLM. 0 = tanpa batas.
    agent_daily_limit: int = 300

    # RAG: PDF panduan kesiapsiagaan (tidak di-commit, taruh di docs/) → vector DB Qdrant.
    knowledge_dir: Path = REPO_ROOT / "docs"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str | None = None          # Qdrant Cloud; kosong untuk Qdrant lokal
    # True: embedding dihitung server Qdrant Cloud (Cloud Inference, model sama: e5-small + bm25),
    # sehingga API tidak perlu memuat model ±470 MB (dipakai di Vercel). False: FastEmbed lokal.
    qdrant_cloud_inference: bool = False
    qdrant_collection: str = "siaganusa-panduan"
    # Model embedding dense RAG (pipeline/knowledge.py). Mengganti model: sesuaikan EMBED_DIM, lalu
    # bangun ulang koleksi (`python -m pipeline.run knowledge`; untuk Vercel jalankan dengan QDRANT_URL/
    # QDRANT_API_KEY Qdrant Cloud, dan modelnya harus tersedia di Qdrant Cloud Inference).
    embed_model: str = "intfloat/multilingual-e5-small"
    embed_dim: int = 384
    # Awalan teks yang diminta keluarga model tertentu. Tidak diisi = otomatis: model e5 memakai
    # "query: " / "passage: ", model lain tanpa awalan.
    embed_query_prefix: str | None = None
    embed_doc_prefix: str | None = None

    # env_ignore_empty: baris kosong di .env (mis. "GEMINI_MODEL=") tidak menimpa default.
    # SIAGA_ENV_FILE: tes mengarahkannya ke file kosong supaya tidak terpengaruh .env pribadi.
    model_config = SettingsConfigDict(env_file=os.environ.get("SIAGA_ENV_FILE", REPO_ROOT / ".env"),
                                      case_sensitive=False, extra="ignore",
                                      env_ignore_empty=True)

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, v: str) -> str:
        """URL dari Supabase/Neon ('postgresql://' atau 'postgres://') → driver psycopg 3 SQLAlchemy."""
        for prefix in ("postgresql://", "postgres://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def db_transaction_pooler(self) -> bool:
        """Supabase transaction pooler (port 6543): koneksi pendek, tanpa prepared statement."""
        from urllib.parse import urlsplit

        return urlsplit(self.database_url).port == 6543

    @property
    def snapshot_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"


settings = Settings()

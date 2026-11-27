"""Pengamanan API (pola sesi 10): header `X-API-Key` dicek di dependency + batas request per IP.

Dasbor boleh dibuka publik (BASIC_AUTH_PASSWORD kosong), jadi browser TIDAK memegang kunci apa pun;
kunci di JavaScript bisa dibaca siapa saja. Yang dijaga adalah yang mahal atau berbahaya:
- /api/admin/*  wajib X-API-Key (`require_admin`).
- semua /api/*  maksimal API_RATE_PER_MIN request/menit per IP (`rate_limit`).
- /api/chat     tambahan AGENT_RATE_PER_MIN pertanyaan/menit per IP (`chat_rate_limit`), plus batas
                harian global AGENT_DAILY_LIMIT di api/main.py (dihitung dari agent_logs).
Klien dengan X-API-Key valid (skrip, Postman, mitra) bebas dari batas per IP.

Penghitung per IP ada di memori proses. Di Vercel tiap instance punya penghitung sendiri, jadi ini
rem kasar terhadap spam, bukan angka pasti. Batas harian agen dihitung di database sehingga berlaku
lintas instance.
"""

import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from pipeline.config import settings

api_key_header = APIKeyHeader(
    name="X-API-Key", auto_error=False,
    description="Nilai API_KEY di .env. Wajib untuk /api/admin; di endpoint lain opsional (bebas batas request).",
)


def key_valid(key: str | None) -> bool:
    """Bandingkan waktu-konstan supaya kunci tidak bisa ditebak dari lama respons."""
    return bool(settings.api_key and key and secrets.compare_digest(key.encode(), settings.api_key.encode()))


def client_ip(request: Request) -> str:
    # X-Real-IP diisi nginx (Docker/tunnel) dan edge Vercel, menimpa nilai kiriman klien.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


class SlidingWindow:
    """Jendela geser 60 detik per kunci (IP)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def over(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > 10_000:  # buang IP yang sudah diam supaya memori tidak tumbuh terus
                for k in [k for k, q in self._hits.items() if not q or now - q[-1] > 60]:
                    del self._hits[k]
            q = self._hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= limit:
                return True
            q.append(now)
            return False


_api_window = SlidingWindow()
_chat_window = SlidingWindow()


def rate_limit(request: Request, key: str | None = Security(api_key_header)) -> None:
    if key_valid(key):
        return
    if _api_window.over(client_ip(request), settings.api_rate_per_min):
        raise HTTPException(status_code=429, detail="Terlalu banyak request. Coba lagi sebentar lagi.",
                            headers={"Retry-After": "60"})


def chat_rate_limit(request: Request, key: str | None = Security(api_key_header)) -> None:
    if key_valid(key):
        return
    if _chat_window.over(client_ip(request), settings.agent_rate_per_min):
        raise HTTPException(status_code=429, detail="Terlalu banyak pertanyaan. Tunggu sebentar lalu coba lagi.",
                            headers={"Retry-After": "60"})


def require_admin(key: str | None = Security(api_key_header)) -> None:
    if not settings.api_key:
        raise HTTPException(status_code=503, detail="Endpoint admin dimatikan: API_KEY belum diisi di .env")
    if not key_valid(key):
        raise HTTPException(status_code=401, detail="Header X-API-Key salah atau tidak ada")

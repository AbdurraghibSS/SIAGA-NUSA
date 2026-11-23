"""Debit sungai GloFAS lewat Open-Meteo Flood API · river discharge.

- Riwayat tersedia sejak 1984; di sini diambil mulai 2010 untuk persentil musiman.
- Nilai harian dihitung per hari **UTC**. Parameter `timezone` justru menggeser
  angkanya satu hari, jadi permintaan dibiarkan dalam UTC.
- Bobot kuota Open-Meteo naik dengan jumlah lokasi × hari, jadi riwayat ditarik per
  tahun dan disimpan ke `data/raw/glofas/daily_<tahun>.json` (bisa dilanjutkan
  kalau terputus). Jawaban 429 ditunggu sampai jendela per menit lewat.
"""

import json
import logging
import time
from datetime import date
from pathlib import Path

from pipeline.rivers import RiverPoint

log = logging.getLogger(__name__)

SOURCE = "glofas"
URL = "https://flood-api.open-meteo.com/v1/flood"
HISTORY_START_YEAR = 2010
RATE_LIMIT_WAIT_S = 65


def _get(session, points: tuple[RiverPoint, ...], **params) -> list[dict]:
    query = {
        "latitude": ",".join(str(p.lat) for p in points),
        "longitude": ",".join(str(p.lon) for p in points),
        "daily": "river_discharge",
        **params,
    }
    for attempt in range(4):
        resp = session.get(URL, params=query, timeout=180)
        if resp.status_code != 429:
            break
        log.info("glofas: kuota per menit habis, menunggu %d detik", RATE_LIMIT_WAIT_S)
        time.sleep(RATE_LIMIT_WAIT_S)
    resp.raise_for_status()
    payload = resp.json()
    items = payload if isinstance(payload, list) else [payload]
    if len(items) != len(points):
        raise ValueError(f"glofas: {len(items)} lokasi, diharapkan {len(points)}")
    return items


def fetch_recent(session, points: tuple[RiverPoint, ...], past_days: int = 14, forecast_days: int = 7) -> list[dict]:
    """Beberapa hari terakhir + prakiraan ke depan, urutan sama dengan `points`."""
    return _get(session, points, past_days=past_days, forecast_days=forecast_days)


def backfill(session, points: tuple[RiverPoint, ...], dest_dir: Path, today: date) -> list[Path]:
    """Tarik riwayat per tahun ke file. Tahun lampau yang sudah ada dilewati; tahun berjalan ditarik ulang."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for year in range(HISTORY_START_YEAR, today.year + 1):
        path = dest_dir / f"daily_{year}.json"
        if path.exists() and year < today.year:
            continue
        end = date(year, 12, 31) if year < today.year else today
        items = _get(session, points, start_date=f"{year}-01-01", end_date=f"{end}")
        path.write_text(json.dumps(items), encoding="utf-8")
        log.info("glofas: %s ditulis", path.name)
        written.append(path)
    return written

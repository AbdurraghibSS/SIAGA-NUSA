"""Arsip prakiraan yang terbit sehari sebelumnya · Open-Meteo Previous Runs API.

Kenapa bukan Historical Forecast API: arsip itu disusun dari jam-jam awal setiap run,
sehingga nilainya untuk hari H **identik dengan run hari H sendiri** (dicek: korelasi
1,000, selisih 0,00 mm, Des 2025–Feb 2026 Jakarta). Dipakai sebagai "prakiraan besok",
model akan mendapat contekan. Variabel `*_previous_day1` di Previous Runs berasal dari
run ±24 jam sebelumnya, yaitu yang benar-benar tersedia saat prediksi dibuat.

- Tersedia sejak **Februari 2024** (Januari 2024 masih kosong).
- `precipitation` (tanpa akhiran) = run hari itu sendiri; dipakai hanya untuk hari yang
  sudah lewat (hujan kemarin, 3 dan 7 hari terakhir).
- Ditarik per model per tahun ke `data/raw/open-meteo/previous_runs_<model>_<tahun>.json`.
"""

import json
import logging
import time
from datetime import date
from pathlib import Path

from pipeline.locations import Location

log = logging.getLogger(__name__)

URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
START = date(2024, 2, 1)
MODELS = ("best_match", "ecmwf_ifs025", "gfs_seamless", "icon_seamless")
HOURLY = (
    "precipitation",                       # run hari itu (hanya untuk hari lampau)
    "precipitation_previous_day1",
    "cape_previous_day1",                  # hanya best_match, GFS, CMA; model lain null
    "relative_humidity_2m_previous_day1",
    "cloud_cover_previous_day1",
    "pressure_msl_previous_day1",
    "wind_speed_10m_previous_day1",
)
RATE_LIMIT_WAIT_S = 65


def _get(session, locations: tuple[Location, ...], model: str, start: date, end: date) -> list[dict]:
    params = {
        "latitude": ",".join(str(l.lat) for l in locations),
        "longitude": ",".join(str(l.lon) for l in locations),
        "hourly": ",".join(HOURLY),
        "models": model,
        "start_date": f"{start}",
        "end_date": f"{end}",
        "timezone": "Asia/Jakarta",  # sama dengan label ERA5 harian (00–24 WIB)
    }
    for _ in range(5):
        resp = session.get(URL, params=params, timeout=300)
        if resp.status_code != 429:
            break
        log.info("previous runs: kuota per menit habis, menunggu %d detik", RATE_LIMIT_WAIT_S)
        time.sleep(RATE_LIMIT_WAIT_S)
    resp.raise_for_status()
    payload = resp.json()
    items = payload if isinstance(payload, list) else [payload]
    if len(items) != len(locations):
        raise ValueError(f"previous runs: {len(items)} lokasi, diharapkan {len(locations)}")
    return items


def backfill(session, locations: tuple[Location, ...], dest_dir: Path, today: date) -> list[Path]:
    """Tarik per model per tahun. Tahun lampau yang sudah ada dilewati; tahun berjalan ditarik ulang
    sampai besok (prakiraan besok ikut, untuk prediksi hari ini)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for model in MODELS:
        for year in range(START.year, today.year + 1):
            path = dest_dir / f"previous_runs_{model}_{year}.json"
            if path.exists() and year < today.year:
                continue
            start = max(START, date(year, 1, 1))
            end = date(year, 12, 31) if year < today.year else today
            items = _get(session, locations, model, start, end)
            path.write_text(json.dumps(items), encoding="utf-8")
            log.info("previous runs: %s ditulis", path.name)
            written.append(path)
    return written

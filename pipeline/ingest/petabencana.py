"""Arsip laporan PetaBencana.id (`/reports/archive`), ditarik per bulan WIB.

Catatan hasil investigasi (Nov 2026):
- Jendela waktu bisa dijumlahkan dan tidak ada batas jumlah hasil, tapi bulan
  yang sangat besar (mis. April 2025, ±23 ribu laporan) mengembalikan HTTP 500.
  Bulan seperti itu diambil ulang per minggu.
- Arsip hanya berisi laporan `confirmed`, termasuk laporan latihan dan uji.
  Penyaringannya ada di `pipeline.clean.petabencana`.
Atribusi: PetaBencana.id. Jangan pernah mengirim laporan ke sistem aslinya.

    python -m pipeline.ingest.petabencana --start 2017-01 --end 2026-11 --out data/raw/petabencana
"""

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from pipeline.ingest.http import make_session

URL = "https://data.petabencana.id/reports/archive"
TIMEOUT_S = 300


def _month_starts(start: date, end: date):
    d = start.replace(day=1)
    while d <= end:
        yield d
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def _next_month(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def _week_windows(start: date, end: date):
    d = start
    while d < end:
        yield d, min(d + timedelta(days=7), end)
        d += timedelta(days=7)


def _params(start: date, end: date) -> dict[str, str]:
    return {"start": f"{start}T00:00:00+0700", "end": f"{end}T00:00:00+0700", "geoformat": "geojson"}


def fetch_window(session: requests.Session, start: date, end: date) -> list[dict]:
    resp = session.get(URL, params=_params(start, end), timeout=TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()["result"]["features"]


def fetch_month(session: requests.Session, month: date) -> tuple[list[dict], str]:
    """Kembalikan (features, mode). Kalau satu bulan gagal, ulangi per minggu."""
    end = _next_month(month)
    try:
        return fetch_window(session, month, end), "month"
    except requests.HTTPError:
        features = []
        for s, e in _week_windows(month, end):
            features += fetch_window(session, s, e)
            time.sleep(1)
        return features, "weekly"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill arsip PetaBencana per bulan")
    parser.add_argument("--start", required=True, help="YYYY-MM")
    parser.add_argument("--end", required=True, help="YYYY-MM (inklusif)")
    parser.add_argument("--out", type=Path, default=Path("data/raw/petabencana"))
    parser.add_argument("--refresh", action="store_true", help="tarik ulang bulan yang sudah ada")
    args = parser.parse_args(argv)

    start = datetime.strptime(args.start, "%Y-%m").date()
    end = datetime.strptime(args.end, "%Y-%m").date()
    args.out.mkdir(parents=True, exist_ok=True)
    session = make_session()
    failed = 0
    for month in _month_starts(start, end):
        path = args.out / f"archive_{month:%Y-%m}.json"
        if path.exists() and not args.refresh:
            continue
        try:
            features, mode = fetch_month(session, month)
        except (requests.RequestException, ValueError, KeyError) as exc:
            print(f"{month:%Y-%m} FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
            failed += 1
            continue
        record = {
            "params": _params(month, _next_month(month)) | {"mode": mode},
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "features": features,
        }
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        print(f"{month:%Y-%m} {len(features)} ({mode})")
        time.sleep(1)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

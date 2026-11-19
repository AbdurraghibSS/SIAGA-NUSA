"""Arsip mentah prakiraan · raw forecast snapshots.

Setiap panggilan disimpan apa adanya di dalam envelope (sumber, lokasi, waktu
ambil, permintaan, status) dan tidak pernah ditimpa. Parsing dan validasi
dilakukan belakangan oleh pipeline, dari arsip ini.

    python -m pipeline.ingest.snapshot --out snapshots

Tata letak: <out>/<sumber>/<YYYY-MM-DD>/<HHMM>Z/<lokasi>.json (UTC)
Exit code 1 hanya kalau semua panggilan gagal. Kegagalan sebagian tetap dicatat
di envelope dan dilaporkan (sebagai ::warning:: di GitHub Actions), tapi exit 0.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from pipeline.ingest import bmkg, openmeteo
from pipeline.ingest.http import TIMEOUT_S, make_session
from pipeline.locations import PILOT_LOCATIONS, Location

SOURCES = (bmkg.SOURCE, openmeteo.SOURCE)

# Open-Meteo sesekali menggantung (ReadTimeout di semua retry urllib3, mis. 13 & 16 Nov 2026).
# Satu panggilan ulang setelah jeda biasanya cukup supaya slot snapshot tidak bolong.
OPENMETEO_RETRY_DELAY_S = 60.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _envelope(source, location, url, params, fetched_at, status, payload, error) -> dict:
    return {
        "source": source,
        "location": location,
        "fetched_at": _iso(fetched_at),
        "request": {"url": url, "params": params},
        "status": status,
        "error": error,
        "payload": payload,
    }


def _get(session: requests.Session, url: str, params: dict) -> tuple[int | None, object, str | None]:
    """Kembalikan (status HTTP, JSON, pesan error). Tidak pernah melempar exception."""
    try:
        resp = session.get(url, params=params, timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        return None, None, f"{type(exc).__name__}: {exc}"
    try:
        payload = resp.json()
    except ValueError:
        return resp.status_code, None, f"invalid JSON: {resp.text[:200]!r}"
    if resp.status_code != 200:
        return resp.status_code, payload, f"HTTP {resp.status_code}"
    return resp.status_code, payload, None


def snapshot_bmkg(session, locations: tuple[Location, ...], delay_s: float = 1.0) -> list[dict]:
    envelopes = []
    for i, loc in enumerate(locations):
        if i and delay_s:
            time.sleep(delay_s)
        params = bmkg.params_for(loc)
        status, payload, error = _get(session, bmkg.URL, params)
        envelopes.append(
            _envelope(bmkg.SOURCE, loc.slug, bmkg.URL, params, _utc_now(), status, payload, error)
        )
    return envelopes


def snapshot_openmeteo(
    session, locations: tuple[Location, ...], retry_delay_s: float = OPENMETEO_RETRY_DELAY_S
) -> list[dict]:
    params = openmeteo.params_for(locations)
    status, payload, error = _get(session, openmeteo.URL, params)
    if status is None and retry_delay_s:
        # Gagal di level jaringan (timeout/koneksi). 429/5xx sudah di-retry oleh sesi HTTP.
        print(f"open-meteo: {error.split(':')[0]}, coba lagi dalam {retry_delay_s:.0f} s", file=sys.stderr)
        time.sleep(retry_delay_s)
        status, payload, error = _get(session, openmeteo.URL, params)
    fetched_at = _utc_now()
    # Kalau gagal, respons mentah (mis. {"error": true, "reason": ...}) disimpan di setiap lokasi.
    items = [payload] * len(locations)
    if error is None:
        try:
            items = openmeteo.split(payload, locations)
        except ValueError as exc:
            error = str(exc)
    return [
        _envelope(openmeteo.SOURCE, loc.slug, openmeteo.URL, params, fetched_at, status, item, error)
        for loc, item in zip(locations, items)
    ]


def snapshot_path(out: Path, run_at: datetime, source: str, location: str) -> Path:
    return out / source / run_at.strftime("%Y-%m-%d") / run_at.strftime("%H%MZ") / f"{location}.json"


def write(envelopes: list[dict], out: Path, run_at: datetime) -> list[Path]:
    paths = []
    for env in envelopes:
        path = snapshot_path(out, run_at, env["source"], env["location"])
        path.parent.mkdir(parents=True, exist_ok=True)
        # x = jangan pernah menimpa snapshot yang sudah ada
        with path.open("x", encoding="utf-8") as f:
            json.dump(env, f, ensure_ascii=False, separators=(",", ":"))
        paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("snapshots"))
    parser.add_argument("--sources", default=",".join(SOURCES), help="comma-separated: " + ",".join(SOURCES))
    args = parser.parse_args(argv)

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = set(sources) - set(SOURCES)
    if unknown:
        parser.error(f"unknown source(s): {', '.join(sorted(unknown))}")

    run_at = _utc_now()
    session = make_session()
    envelopes: list[dict] = []
    if bmkg.SOURCE in sources:
        envelopes += snapshot_bmkg(session, PILOT_LOCATIONS)
    if openmeteo.SOURCE in sources:
        envelopes += snapshot_openmeteo(session, PILOT_LOCATIONS)

    write(envelopes, args.out, run_at)
    failed = [e for e in envelopes if e["error"]]
    print(f"{_iso(run_at)} wrote {len(envelopes)} snapshots, {len(failed)} failed")
    for e in failed:
        print(f"  FAIL {e['source']}/{e['location']}: {e['error']}", file=sys.stderr)
    if failed and os.environ.get("GITHUB_ACTIONS") == "true":
        for source in sources:
            n_fail = sum(e["source"] == source for e in failed)
            if n_fail:
                n_total = sum(e["source"] == source for e in envelopes)
                print(f"::warning title=Snapshot {source}::{n_fail}/{n_total} lokasi gagal, lihat field error di envelope")
    # Merah hanya kalau tidak ada yang berhasil sama sekali; sebagian gagal = warning saja.
    return 1 if envelopes and len(failed) == len(envelopes) else 0


if __name__ == "__main__":
    sys.exit(main())

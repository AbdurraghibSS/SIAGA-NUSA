"""Snapshot mentah → tabel bersih · pandas data wrangling (sesi 6).

Langkah yang sama untuk tiap sumber:
1. Ratakan JSON bersarang menjadi satu baris per (lokasi, run, jam).
2. Konversi tipe: teks waktu → `datetime` UTC, angka → float.
3. Buang duplikat (BMKG: terbitan yang sama muncul di beberapa snapshot).
4. Validasi rentang nilai. Baris di luar rentang masuk karantina, tidak diperbaiki.
5. Nilai kosong dibiarkan kosong (NaN). Angka hujan tidak pernah diisi tebakan.
"""

import json
from pathlib import Path

import pandas as pd

from pipeline.locations import Location

# Rentang wajar per kolom (inklusif). NaN tidak dianggap pelanggaran.
BMKG_RULES = {
    "precip_mm": (0, 500),
    "temperature_c": (-5, 45),
    "humidity_pct": (0, 100),
    "cloud_cover_pct": (0, 100),
    "wind_speed_kmh": (0, 200),
}
OPENMETEO_RULES = {
    "precip_mm": (0, 300),
    "rain_mm": (0, 300),
    "precip_prob_pct": (0, 100),
    "temperature_c": (-5, 45),
    "humidity_pct": (0, 100),
    "pressure_hpa": (900, 1100),
    "wind_speed_kmh": (0, 300),
    "wind_dir_deg": (0, 360),
    "cloud_cover_pct": (0, 100),
}
OPENMETEO_COLUMNS = {
    "precipitation": "precip_mm",
    "rain": "rain_mm",
    "precipitation_probability": "precip_prob_pct",
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "humidity_pct",
    "pressure_msl": "pressure_hpa",
    "wind_speed_10m": "wind_speed_kmh",
    "wind_direction_10m": "wind_dir_deg",
    "cloud_cover": "cloud_cover_pct",
}


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------
def read_envelopes(snapshot_dir: Path, source: str) -> list[dict]:
    """Baca semua envelope `<dir>/<source>/<tanggal>/<jam>Z/<lokasi>.json`, urut waktu."""
    paths = sorted(Path(snapshot_dir, source).glob("*/*/*.json"))
    return [json.loads(p.read_text(encoding="utf-8")) for p in paths]


def raw_payload_frame(envelopes: list[dict]) -> pd.DataFrame:
    """Envelope apa adanya untuk tabel `raw_payloads` (lapisan ELT), termasuk yang gagal."""
    df = pd.DataFrame([
        {
            "source": e["source"],
            "location": e["location"],
            "fetched_at": e["fetched_at"],
            "status": e.get("status"),
            "error": e.get("error"),
            "payload": json.dumps(e.get("payload"), ensure_ascii=False),
        }
        for e in envelopes
    ])
    if not df.empty:
        df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True)
        df["status"] = df["status"].astype("Int64")
    return df


def concat_rejects(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Gabungkan potongan baris ditolak; selalu punya kolom `reason`."""
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["reason"])


def _failed(envelopes: list[dict]) -> pd.DataFrame:
    rows = [
        {"reason": f"fetch_failed: {e['error']}", "source": e["source"], "location": e["location"], "fetched_at": e["fetched_at"]}
        for e in envelopes if e.get("error") or not e.get("payload")
    ]
    return pd.DataFrame(rows, columns=["reason", "source", "location", "fetched_at"])


# ---------------------------------------------------------------------------
# Validasi
# ---------------------------------------------------------------------------
def split_invalid(df: pd.DataFrame, rules: dict[str, tuple[float, float]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pisahkan baris valid dan tidak valid. Baris tidak valid mendapat kolom `reason`."""
    problems = []
    for col, (lo, hi) in rules.items():
        bad = df[col].notna() & ~df[col].between(lo, hi)
        problems.append(bad.map({True: f"{col} di luar {lo}–{hi}", False: ""}))
    reasons = pd.concat(problems, axis=1).apply(lambda r: "; ".join(x for x in r if x), axis=1)
    invalid = reasons != ""
    return df[~invalid].copy(), df[invalid].assign(reason=reasons[invalid])


# ---------------------------------------------------------------------------
# BMKG
# ---------------------------------------------------------------------------
def bmkg_frame(envelopes: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Prakiraan BMKG per 3 jam → (baris bersih, baris ditolak).

    `analysis_date` BMKG tidak membawa zona waktu; nilainya jam run model (00/12),
    jadi dibaca sebagai UTC. `datetime` sudah UTC (berakhiran Z).
    """
    rows, empty = [], []
    for e in envelopes:
        if e.get("error") or not e.get("payload"):
            continue
        blocks = [b for b in (e["payload"].get("data") or []) if b and b.get("cuaca")]
        if not blocks:
            # Mis. 21 Nov 2026 02.19 UTC: HTTP 200 untuk 8 kota, tetapi "cuaca": null.
            empty.append({"reason": "BMKG membalas tanpa prakiraan (cuaca kosong)", "source": e["source"],
                          "location": e["location"], "fetched_at": e["fetched_at"]})
            continue
        for block in blocks:
            for day in block["cuaca"]:
                for item in day or []:
                    rows.append({
                        "location": e["location"],
                        "fetched_at": e["fetched_at"],
                        "analysis_at": item.get("analysis_date"),
                        "valid_at": item.get("datetime"),
                        "weather_code": item.get("weather"),
                        "weather_desc": item.get("weather_desc"),
                        "precip_mm": item.get("tp"),
                        "temperature_c": item.get("t"),
                        "humidity_pct": item.get("hu"),
                        "cloud_cover_pct": item.get("tcc"),
                        "wind_speed_kmh": item.get("ws"),
                        "wind_from": item.get("wd"),
                    })
    failed = concat_rejects([_failed(envelopes), pd.DataFrame(empty)])
    if not rows:
        return pd.DataFrame(), failed

    df = pd.DataFrame(rows)
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True)
    df["valid_at"] = pd.to_datetime(df["valid_at"], utc=True, errors="coerce")
    df["analysis_at"] = pd.to_datetime(df["analysis_at"], errors="coerce").dt.tz_localize("UTC")
    for col in BMKG_RULES:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    df["weather_code"] = pd.to_numeric(df["weather_code"], errors="coerce").astype("Int64")
    df["weather_desc"] = df["weather_desc"].astype("string").str.strip()
    df["wind_from"] = df["wind_from"].astype("string").str.strip().str.upper()

    no_time = df["valid_at"].isna() | df["analysis_at"].isna()
    rejects = [failed, df[no_time].assign(reason="waktu tidak bisa dibaca")]
    df = df[~no_time]

    # Terbitan yang sama muncul di beberapa snapshot: simpan yang paling awal diambil.
    df = (df.sort_values("fetched_at")
            .drop_duplicates(["location", "analysis_at", "valid_at"], keep="first")
            .rename(columns={"fetched_at": "first_fetched_at"}))

    valid, invalid = split_invalid(df, BMKG_RULES)
    rejects.append(invalid)
    return valid.reset_index(drop=True), concat_rejects(rejects)


# ---------------------------------------------------------------------------
# Open-Meteo
# ---------------------------------------------------------------------------
def openmeteo_frame(envelopes: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Prakiraan Open-Meteo per jam → (baris bersih, baris ditolak). Format lebar → panjang."""
    frames = []
    for e in envelopes:
        if e.get("error") or not e.get("payload"):
            continue
        hourly = e["payload"].get("hourly") or {}
        if "time" not in hourly:
            continue
        part = pd.DataFrame(hourly).rename(columns={"time": "valid_at", **OPENMETEO_COLUMNS})
        part.insert(0, "issued_at", e["fetched_at"])
        part.insert(0, "location", e["location"])
        frames.append(part)
    failed = _failed(envelopes)
    if not frames:
        return pd.DataFrame(), failed

    df = pd.concat(frames, ignore_index=True)
    df["issued_at"] = pd.to_datetime(df["issued_at"], utc=True)
    df["valid_at"] = pd.to_datetime(df["valid_at"], utc=True)  # permintaan memakai timezone=UTC
    for col in OPENMETEO_RULES:
        df[col] = pd.to_numeric(df.get(col), errors="coerce").astype("float64")
    df = df[["location", "issued_at", "valid_at", *OPENMETEO_RULES]]
    df = df.drop_duplicates(["location", "issued_at", "valid_at"])

    valid, invalid = split_invalid(df, OPENMETEO_RULES)
    return valid.reset_index(drop=True), concat_rejects([failed, invalid])


# ---------------------------------------------------------------------------
# ERA5 harian
# ---------------------------------------------------------------------------
def era5_frame(path: Path, locations: tuple[Location, ...], dataset: str) -> pd.DataFrame:
    """Arsip harian dari file (urutan sama dengan `locations`) → satu baris per (lokasi, tanggal)."""
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    return era5_items_frame(items, locations, dataset, label=Path(path).name)


def era5_items_frame(items: list[dict], locations: tuple[Location, ...], dataset: str, label: str = "api") -> pd.DataFrame:
    """Respons arsip harian Open-Meteo → baris (lokasi, tanggal, dataset, precip_mm).

    Hari yang belum tersedia (ERA5 tertinggal ±5 hari, nilainya null) dibuang, bukan
    disimpan kosong: baris kosong akan menghalangi angka aslinya masuk nanti.
    """
    if len(items) != len(locations):
        raise ValueError(f"{label}: {len(items)} lokasi, diharapkan {len(locations)}")
    frames = []
    for loc, item in zip(locations, items):
        # Grid ERA5 ±25 km, jadi koordinat respons bergeser; >0,5° berarti urutan tertukar.
        if abs(item["latitude"] - loc.lat) > 0.5 or abs(item["longitude"] - loc.lon) > 0.5:
            raise ValueError(f"{label}: koordinat {item['latitude']},{item['longitude']} bukan {loc.slug}")
        daily = item["daily"]
        frames.append(pd.DataFrame({
            "location": loc.slug,
            "date": pd.to_datetime(daily["time"]).date,
            "dataset": dataset,
            "precip_mm": pd.to_numeric(pd.Series(daily["precipitation_sum"]), errors="coerce").astype("float64"),
        }))
    df = pd.concat(frames, ignore_index=True)
    return df[df["precip_mm"].notna() & (df["precip_mm"] >= 0)].reset_index(drop=True)

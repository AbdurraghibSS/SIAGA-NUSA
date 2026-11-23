"""Transform arsip Previous Runs · per jam → ringkasan harian WIB per (kota, tanggal, model)."""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.locations import Location

# Grid model ±10–25 km; koordinat respons bergeser, >0,5° berarti urutan tertukar.
MAX_SHIFT_DEG = 0.5
FILE_RE = re.compile(r"previous_runs_(?P<model>.+)_(?P<year>\d{4})\.json$")

# kolom harian → (variabel per jam, agregasi)
DAILY = {
    "precip_d0_mm": ("precipitation", "sum"),
    "precip_d1_mm": ("precipitation_previous_day1", "sum"),
    "precip_d1_max_mm_h": ("precipitation_previous_day1", "max"),
    "cape_d1_max": ("cape_previous_day1", "max"),
    "rh_d1_mean": ("relative_humidity_2m_previous_day1", "mean"),
    "cloud_d1_mean": ("cloud_cover_previous_day1", "mean"),
    "pressure_d1_mean": ("pressure_msl_previous_day1", "mean"),
    "wind_d1_max": ("wind_speed_10m_previous_day1", "max"),
}
MIN_HOURS = 24  # jumlah harian hanya sah kalau 24 jam lengkap; agregat lain cukup ≥18 jam
MIN_HOURS_OTHER = 18


def daily_frame(items: list[dict], locations: tuple[Location, ...], model: str, label: str = "api") -> pd.DataFrame:
    """Respons per jam (zona Asia/Jakarta) → satu baris per (lokasi, tanggal) untuk satu model.

    Hari yang jamnya tidak lengkap diberi NaN untuk kolom itu, bukan dihitung dari
    sebagian jam: jumlah hujan dari 12 jam akan terlihat seperti hari kering.
    """
    if len(items) != len(locations):
        raise ValueError(f"{label}: {len(items)} lokasi, diharapkan {len(locations)}")
    frames = []
    for loc, item in zip(locations, items):
        if abs(item["latitude"] - loc.lat) > MAX_SHIFT_DEG or abs(item["longitude"] - loc.lon) > MAX_SHIFT_DEG:
            raise ValueError(f"{label}: koordinat {item['latitude']},{item['longitude']} bukan {loc.slug}")
        hourly = pd.DataFrame(item["hourly"])
        hourly["date"] = pd.to_datetime(hourly["time"]).dt.date
        g = hourly.groupby("date")
        out = pd.DataFrame(index=g.size().index)
        for col, (var, how) in DAILY.items():
            if var not in hourly:
                out[col] = np.nan
                continue
            values = pd.to_numeric(hourly[var], errors="coerce")
            agg = values.groupby(hourly["date"]).agg(how)
            n = values.notna().groupby(hourly["date"]).sum()
            need = MIN_HOURS if how == "sum" else MIN_HOURS_OTHER
            out[col] = agg.where(n >= need)
        out = out.reset_index()
        out.insert(0, "model", model)
        out.insert(0, "location", loc.slug)
        frames.append(out)
    df = pd.concat(frames, ignore_index=True)
    # Baris yang semua nilainya kosong (mis. tanggal sebelum arsip mulai) tidak disimpan.
    return df.dropna(subset=list(DAILY), how="all").reset_index(drop=True)


def files_frame(paths: list[Path], locations: tuple[Location, ...]) -> pd.DataFrame:
    frames = []
    for path in sorted(paths):
        m = FILE_RE.search(path.name)
        if not m:
            continue
        items = json.loads(path.read_text(encoding="utf-8"))
        frames.append(daily_frame(items, locations, m["model"], label=path.name))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

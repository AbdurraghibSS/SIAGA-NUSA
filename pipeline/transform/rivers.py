"""Transform debit GloFAS · respons Open-Meteo Flood → baris (titik, tanggal, debit)."""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.rivers import RiverPoint

# Pusat sel GloFAS selalu kelipatan 0,05° + 0,025°; respons bergeser lebih dari ini = urutan tertukar.
MAX_CELL_SHIFT_DEG = 0.03


def glofas_items_frame(items: list[dict], points: tuple[RiverPoint, ...], today: date,
                       label: str = "api") -> tuple[pd.DataFrame, pd.DataFrame]:
    """→ (baris bersih, baris ditolak).

    - `is_forecast` = tanggal ≥ hari ini (UTC); nilai itu masih akan berubah.
    - Hari tanpa angka dibuang (sama seperti ERA5) supaya tidak menghalangi angka aslinya nanti.
    - Debit negatif ditolak ke karantina.
    """
    if len(items) != len(points):
        raise ValueError(f"{label}: {len(items)} lokasi, diharapkan {len(points)}")
    frames = []
    for point, item in zip(points, items):
        if abs(item["latitude"] - point.lat) > MAX_CELL_SHIFT_DEG or abs(item["longitude"] - point.lon) > MAX_CELL_SHIFT_DEG:
            raise ValueError(f"{label}: sel {item['latitude']},{item['longitude']} bukan {point.slug}")
        daily = item["daily"]
        frames.append(pd.DataFrame({
            "point": point.slug,
            "date": pd.to_datetime(daily["time"]).date,
            "discharge_m3s": pd.to_numeric(pd.Series(daily["river_discharge"]), errors="coerce").astype("float64"),
        }))
    df = pd.concat(frames, ignore_index=True).dropna(subset=["discharge_m3s"])
    df["is_forecast"] = df["date"] >= today
    negative = df["discharge_m3s"] < 0
    rejects = df[negative].assign(reason="debit negatif", file=label)
    return df[~negative].reset_index(drop=True), rejects.reset_index(drop=True)


def glofas_files_frame(paths: list[Path], points: tuple[RiverPoint, ...], today: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gabungkan file riwayat per tahun."""
    cleans, rejects = [], []
    for path in sorted(paths):
        clean, bad = glofas_items_frame(json.loads(path.read_text(encoding="utf-8")), points, today, label=path.name)
        cleans.append(clean)
        rejects.append(bad)
    if not cleans:
        return pd.DataFrame(), pd.DataFrame()
    return pd.concat(cleans, ignore_index=True), pd.concat(rejects, ignore_index=True)

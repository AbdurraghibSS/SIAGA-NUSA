"""Model A · peluang hujan sedang ke atas (ERA5 ≥20 mm/hari WIB) besok, per kota.

Satu baris = (kota, hari target T). Prediksi untuk T dianggap dibuat sepanjang hari T−1,
sama dengan waktu terbitnya run `previous_day1` untuk jam-jam di hari T. Karena itu:

- fitur prakiraan  : run yang terbit sehari sebelumnya untuk hari T, dari 4 model
- fitur hujan lalu : run hari itu sendiri (`precip_d0`) untuk hari T−1, T−3..T−1, T−7..T−1,
                     yang semuanya sudah lewat saat prediksi selesai dibuat
- label            : hujan ERA5 hari T ≥ 20 mm (ERA5 tidak pernah dipakai sebagai fitur)

Fungsi `features_from_daily` dipakai juga saat prediksi langsung, supaya fitur latih dan
fitur produksi dihitung dengan kode yang sama.
"""

import numpy as np
import pandas as pd
from sqlalchemy import text

from pipeline.locations import PILOT_LOCATIONS

THRESHOLD_MM = 20.0
EXTREME_MM = 50.0
MODELS = ("best_match", "ecmwf_ifs025", "gfs_seamless", "icon_seamless")
SHORT = {"best_match": "bm", "ecmwf_ifs025": "ecmwf", "gfs_seamless": "gfs", "icon_seamless": "icon"}
CITIES = tuple(l.slug for l in PILOT_LOCATIONS)

FC_COLS = [f"fc_{SHORT[m]}_mm" for m in MODELS]
FEATURES = [
    *FC_COLS,
    "fc_mean_mm", "fc_max_mm", "fc_spread_mm", "fc_n_models_ge20",
    "fc_bm_max_mm_h", "cape_max", "rh_mean", "cloud_mean", "pressure_mean", "wind_max",
    "rain_1d_mm", "rain_3d_mm", "rain_7d_mm",
    "month_sin", "month_cos",
    *[f"city_{c}" for c in CITIES],
]

# Pembagian berdasarkan waktu (hari target). Arsip previous_day1 mulai 1 Feb 2024;
# 8 hari pertama dipakai untuk menghitung hujan 7 hari terakhir.
SPLITS = {
    "train": ("2024-02-09", "2025-06-30"),
    "val": ("2025-07-01", "2025-12-31"),
    "test": ("2026-01-01", "2099-12-31"),
}


def load_archive(engine) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text("SELECT * FROM forecast_archive_daily"), conn, parse_dates=["date"])


def load_labels(engine) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(
            "SELECT location, date, precip_mm::float AS era5_mm FROM obs_daily WHERE dataset = 'era5'"
        ), conn, parse_dates=["date"])


def features_from_daily(archive: pd.DataFrame) -> pd.DataFrame:
    """Arsip harian (location, date, model, …) → satu baris fitur per (location, date=T)."""
    wide = archive.pivot_table(index=["location", "date"], columns="model",
                               values=["precip_d0_mm", "precip_d1_mm"], aggfunc="first")
    wide.columns = [f"{v}__{m}" for v, m in wide.columns]
    wide = wide.reset_index()
    bm = archive[archive["model"] == "best_match"].set_index(["location", "date"])

    out = wide[["location", "date"]].copy()
    for m in MODELS:
        out[f"fc_{SHORT[m]}_mm"] = wide.get(f"precip_d1_mm__{m}")
    fc = out[FC_COLS]
    out["fc_mean_mm"] = fc.mean(axis=1)
    out["fc_max_mm"] = fc.max(axis=1)
    out["fc_spread_mm"] = fc.std(axis=1)
    out["fc_n_models_ge20"] = (fc >= THRESHOLD_MM).sum(axis=1).where(fc.notna().any(axis=1))

    key = pd.MultiIndex.from_frame(out[["location", "date"]])
    for col, src in [("fc_bm_max_mm_h", "precip_d1_max_mm_h"), ("cape_max", "cape_d1_max"), ("rh_mean", "rh_d1_mean"),
                     ("cloud_mean", "cloud_d1_mean"), ("pressure_mean", "pressure_d1_mean"), ("wind_max", "wind_d1_max")]:
        out[col] = bm[src].reindex(key).to_numpy()

    # Hujan yang sudah lewat: run hari itu sendiri (best_match) untuk T−1 dan sebelumnya.
    past = wide[["location", "date", "precip_d0_mm__best_match"]].rename(columns={"precip_d0_mm__best_match": "d0"})
    past = past.set_index("date").groupby("location")["d0"]
    full_days = lambda s: s.asfreq("D")  # noqa: E731  tanggal hilang → NaN, bukan digeser
    roll = {}
    for loc, s in past:
        s = full_days(s.sort_index())
        roll[loc] = pd.DataFrame({
            "rain_1d_mm": s.shift(1),
            "rain_3d_mm": s.shift(1).rolling(3, min_periods=3).sum(),
            "rain_7d_mm": s.shift(1).rolling(7, min_periods=7).sum(),
        })
    roll_df = pd.concat(roll, names=["location", "date"]).reset_index()
    out = out.merge(roll_df, on=["location", "date"], how="left")

    month = out["date"].dt.month
    out["month_sin"] = np.sin(2 * np.pi * month / 12)
    out["month_cos"] = np.cos(2 * np.pi * month / 12)
    for c in CITIES:
        out[f"city_{c}"] = (out["location"] == c).astype(int)
    return out


def build_dataset(engine) -> pd.DataFrame:
    feats = features_from_daily(load_archive(engine))
    df = feats.merge(load_labels(engine), on=["location", "date"], how="inner")
    df = df.dropna(subset=["fc_bm_mm", "era5_mm", "rain_7d_mm"]).reset_index(drop=True)
    df["y"] = (df["era5_mm"] >= THRESHOLD_MM).astype(int)
    df["y_extreme"] = (df["era5_mm"] >= EXTREME_MM).astype(int)
    df["split"] = None
    for name, (a, b) in SPLITS.items():
        df.loc[df["date"].between(a, b), "split"] = name
    return df.dropna(subset=["split"]).reset_index(drop=True)


def baseline_rule(df: pd.DataFrame) -> np.ndarray:
    """Aturan pembanding (plan §6.2): prakiraan best_match untuk besok ≥ 20 mm."""
    return (df["fc_bm_mm"] >= THRESHOLD_MM).astype(int).to_numpy()

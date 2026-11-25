"""Prediksi harian Model A · peluang hujan ≥20 mm besok untuk 8 kota → tabel `rain_predictions`.

Fitur dihitung dengan `features_from_daily`, kode yang sama dengan pelatihan, dengan satu
perbedaan yang disengaja: untuk hari target (besok) dipakai **run terbaru hari ini**.
Saat pelatihan, fitur prakiraan untuk hari T adalah run yang terbit pada T−1
(`*_previous_day1`). Untuk tanggal yang belum terjadi, `*_previous_day1` justru berisi run
kemarin (lebih basi), jadi padanan yang benar adalah variabel dasar dari run terbaru.

Model dimuat dari MLflow lewat alias (`models:/siaganusa-hujan@champion`), sehingga
mengganti juara cukup dengan memindahkan alias.
"""

import logging
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from pipeline import model_a as ma
from pipeline.ingest.previous_runs import fetch
from pipeline.locations import PILOT_LOCATIONS
from pipeline.transform.previous_runs import daily_frame

log = logging.getLogger(__name__)

MODEL_NAME = "siaganusa-hujan"
ALIAS = "champion"
LIVE_VARS = ("cape", "relative_humidity_2m", "cloud_cover", "pressure_msl", "wind_speed_10m")


def as_training_layout(item: dict) -> dict:
    """Respons variabel dasar (run terbaru) → nama kolom yang dikenal `daily_frame`.

    `precipitation` tetap sebagai hujan run hari itu (dipakai untuk hari yang sudah lewat),
    dan juga disalin ke `*_previous_day1` supaya hari target memakai run terbaru.
    """
    hourly = dict(item["hourly"])
    hourly["precipitation_previous_day1"] = hourly.get("precipitation")
    for var in LIVE_VARS:
        hourly[f"{var}_previous_day1"] = hourly.pop(var, None)
    return {**item, "hourly": hourly}


def live_archive(session, today: date) -> pd.DataFrame:
    """9 hari terakhir + besok dari 4 model, dalam bentuk yang sama dengan `forecast_archive_daily`."""
    frames = []
    for model in ma.MODELS:
        # Variabel dasar (tanpa akhiran _previous_dayN) = run terbaru.
        items = fetch(session, PILOT_LOCATIONS, model, today - timedelta(days=9), today + timedelta(days=1),
                      hourly=("precipitation", *LIVE_VARS))
        frames.append(daily_frame([as_training_layout(i) for i in items], PILOT_LOCATIONS, model, label=f"live {model}"))
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    return df


def predict(session, engine, today: date) -> pd.DataFrame:
    import mlflow

    from pipeline.config import settings

    target = pd.Timestamp(today + timedelta(days=1))
    feats = ma.features_from_daily(live_archive(session, today))
    rows = feats[feats["date"] == target].reset_index(drop=True)
    if rows.empty or rows[["fc_bm_mm", "rain_7d_mm"]].isna().any(axis=None):
        raise RuntimeError(f"fitur untuk {target.date()} belum lengkap")

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    version = mlflow.MlflowClient().get_model_version_by_alias(MODEL_NAME, ALIAS)
    model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{ALIAS}")
    prob = model.predict_proba(rows[ma.FEATURES])[:, 1]
    return pd.DataFrame({
        "location": rows["location"],
        "target_date": target.date(),
        "model_name": MODEL_NAME,
        "model_version": str(version.version),
        "issued_at": datetime.now(timezone.utc),
        "prob": prob.round(4),
        "level": [ma.prob_level(p) for p in prob],
    })

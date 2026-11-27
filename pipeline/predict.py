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


def settings_repo_models():
    from pipeline.config import REPO_ROOT

    return REPO_ROOT / "models"


def load_champion(cache_root):
    """Model @champion dari MLflow, disalin ke `cache_root/v<versi>` dan dimuat dari salinan itu.

    Kalau server MLflow tidak bisa dihubungi, salinan champion terakhir yang dipakai (tercatat di
    `cache_root/champion.json`), supaya prediksi harian tidak gagal hanya karena server mati.
    Kembalikan (model, versi, dari_cache)."""
    import json
    import os

    import mlflow

    from pipeline.config import settings

    # Default MLflow mencoba ulang ±4 menit; untuk job terjadwal lebih baik cepat jatuh ke salinan lokal.
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "1")
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "10")
    pointer = cache_root / "champion.json"
    try:
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        version = str(mlflow.MlflowClient().get_model_version_by_alias(MODEL_NAME, ALIAS).version)
        local = cache_root / f"v{version}"
        if not (local / "MLmodel").exists():
            mlflow.artifacts.download_artifacts(artifact_uri=f"models:/{MODEL_NAME}/{version}", dst_path=str(local))
        pointer.write_text(json.dumps({"model": MODEL_NAME, "version": version}), encoding="utf-8")
        from_cache = False
    except Exception as exc:
        if not pointer.exists():
            # Salinan yang di-commit di repo (models/), dipakai GitHub Actions yang tidak menjangkau MLflow.
            bundled = settings_repo_models() / MODEL_NAME
            if (bundled / "champion.json").exists():
                cache_root, pointer = bundled, bundled / "champion.json"
            else:
                raise RuntimeError(f"MLflow tidak bisa dihubungi dan belum ada salinan model: {exc}") from exc
        version = json.loads(pointer.read_text(encoding="utf-8"))["version"]
        local = cache_root / f"v{version}"
        from_cache = True
        log.warning("MLflow tidak bisa dihubungi (%s); memakai salinan %s v%s", type(exc).__name__, MODEL_NAME, version)
    return mlflow.sklearn.load_model(str(local)), version, from_cache


def predict(session, engine, today: date) -> pd.DataFrame:
    from pipeline.config import settings

    target = pd.Timestamp(today + timedelta(days=1))
    feats = ma.features_from_daily(live_archive(session, today))
    rows = feats[feats["date"] == target].reset_index(drop=True)
    if rows.empty or rows[["fc_bm_mm", "rain_7d_mm"]].isna().any(axis=None):
        raise RuntimeError(f"fitur untuk {target.date()} belum lengkap")

    cache_root = settings.data_dir / "models" / MODEL_NAME
    cache_root.mkdir(parents=True, exist_ok=True)
    model, version, _ = load_champion(cache_root)
    prob = model.predict_proba(rows[ma.FEATURES])[:, 1]
    return pd.DataFrame({
        "location": rows["location"],
        "target_date": target.date(),
        "model_name": MODEL_NAME,
        "model_version": version,
        "issued_at": datetime.now(timezone.utc),
        "prob": prob.round(4),
        "level": [ma.prob_level(p) for p in prob],
    })

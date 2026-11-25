from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from pipeline.locations import Location
from pipeline.model_a import MODELS, features_from_daily
from pipeline.transform.previous_runs import daily_frame

LOC = (Location("jakarta", "Jakarta (Kemayoran)", "31.71.03.1001", -6.1647, 106.8454),)


def hourly_item(days: int, d0: float, d1: float, missing_hour: int | None = None):
    times = [f"2025-01-{1 + h // 24:02d}T{h % 24:02d}:00" for h in range(24 * days)]
    p0 = [d0] * len(times)
    if missing_hour is not None:
        p0[missing_hour] = None
    return {"latitude": -6.15, "longitude": 106.85, "hourly": {
        "time": times, "precipitation": p0, "precipitation_previous_day1": [d1] * len(times),
        "cape_previous_day1": [100.0] * len(times), "relative_humidity_2m_previous_day1": [80.0] * len(times),
        "cloud_cover_previous_day1": [50.0] * len(times), "pressure_msl_previous_day1": [1010.0] * len(times),
        "wind_speed_10m_previous_day1": [5.0] * len(times)}}


def test_daily_sum_needs_all_24_hours():
    df = daily_frame([hourly_item(2, d0=1.0, d1=0.5, missing_hour=3)], LOC, "best_match")
    assert np.isnan(df.loc[0, "precip_d0_mm"])          # hari 1 kehilangan satu jam → bukan 23 mm
    assert df.loc[1, "precip_d0_mm"] == pytest.approx(24.0)
    assert df.loc[0, "precip_d1_mm"] == pytest.approx(12.0)
    assert df.loc[0, "precip_d1_max_mm_h"] == pytest.approx(0.5)


def test_daily_frame_rejects_wrong_location():
    item = hourly_item(1, 1, 1)
    item["latitude"] = 3.58
    with pytest.raises(ValueError):
        daily_frame([item], LOC, "best_match")


def _archive(n_days=10):
    rows = []
    for i in range(n_days):
        d = pd.Timestamp("2025-01-01") + timedelta(days=i)
        for k, m in enumerate(MODELS):
            rows.append({"location": "jakarta", "date": d, "model": m, "precip_d0_mm": float(i),
                         "precip_d1_mm": 10.0 + 5 * k, "precip_d1_max_mm_h": 3.0, "cape_d1_max": 500.0,
                         "rh_d1_mean": 85.0, "cloud_d1_mean": 70.0, "pressure_d1_mean": 1009.0, "wind_d1_max": 12.0})
    return pd.DataFrame(rows)


def test_past_rain_uses_only_days_before_target():
    f = features_from_daily(_archive()).set_index("date")
    t = pd.Timestamp("2025-01-08")                     # d0 hari ke-i = i, jadi T−1 = 6
    assert f.loc[t, "rain_1d_mm"] == 6
    assert f.loc[t, "rain_3d_mm"] == 4 + 5 + 6
    assert f.loc[t, "rain_7d_mm"] == sum(range(0, 7))
    assert np.isnan(f.loc[pd.Timestamp("2025-01-03"), "rain_7d_mm"])  # belum ada 7 hari


def test_multi_model_summary():
    f = features_from_daily(_archive()).iloc[-1]
    assert f["fc_bm_mm"] == 10 and f["fc_icon_mm"] == 25
    assert f["fc_mean_mm"] == pytest.approx(17.5)
    assert f["fc_n_models_ge20"] == 2                   # gfs 20, icon 25
    assert f["city_jakarta"] == 1


@pytest.mark.parametrize("p,level", [(0.0, "Rendah"), (0.129, "Rendah"), (0.13, "Sedang"), (0.349, "Sedang"), (0.35, "Tinggi"), (0.99, "Tinggi")])
def test_prob_level(p, level):
    from pipeline.model_a import prob_level
    assert prob_level(p) == level


def test_live_layout_uses_latest_run_for_target_day():
    from pipeline.predict import as_training_layout
    item = {"latitude": -6.15, "longitude": 106.85, "hourly": {
        "time": [f"2025-01-01T{h:02d}:00" for h in range(24)], "precipitation": [2.0] * 24,
        "cape": [300.0] * 24, "relative_humidity_2m": [90.0] * 24, "cloud_cover": [80.0] * 24,
        "pressure_msl": [1008.0] * 24, "wind_speed_10m": [7.0] * 24}}
    df = daily_frame([as_training_layout(item)], LOC, "best_match")
    assert df.loc[0, "precip_d1_mm"] == pytest.approx(48.0)   # run terbaru jadi fitur "prakiraan"
    assert df.loc[0, "precip_d0_mm"] == pytest.approx(48.0)
    assert df.loc[0, "cape_d1_max"] == 300.0

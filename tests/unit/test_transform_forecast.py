import math

import pytest

from pipeline.locations import PILOT_LOCATIONS
from pipeline.transform.forecast import bmkg_frame, era5_items_frame, openmeteo_frame, raw_payload_frame


def bmkg_env(fetched_at, items, location="jakarta", error=None):
    payload = None if error else {"lokasi": {}, "data": [{"lokasi": {}, "cuaca": [items] if items is not None else None}]}
    return {"source": "bmkg", "location": location, "fetched_at": fetched_at, "status": 200, "error": error, "payload": payload}


def bmkg_item(dt, tp=0.3, hu=71, analysis="2026-11-23T00:00:00"):
    return {"datetime": dt, "analysis_date": analysis, "t": 31, "tcc": 99, "tp": tp, "weather": 3,
            "weather_desc": " Berawan ", "wd": "n", "ws": 1.9, "hu": hu}


def test_bmkg_same_issuance_in_two_snapshots_is_kept_once_with_first_fetch():
    items = [bmkg_item("2026-11-23T03:00:00Z"), bmkg_item("2026-11-23T06:00:00Z")]
    clean, rejects = bmkg_frame([
        bmkg_env("2026-11-23T05:00:00Z", items),
        bmkg_env("2026-11-23T02:00:00Z", items),
    ])
    assert len(clean) == 2
    assert (clean["first_fetched_at"].dt.hour == 2).all()
    assert str(clean["analysis_at"].dt.tz) == "UTC"
    assert clean.loc[0, "weather_desc"] == "Berawan"
    assert clean.loc[0, "wind_from"] == "N"
    assert rejects.empty


def test_bmkg_empty_forecast_with_http_200_is_quarantined():
    # Kasus nyata 21 Nov 2026 02.19 UTC: status 200, "cuaca": null untuk semua kota.
    clean, rejects = bmkg_frame([bmkg_env("2026-11-21T02:19:00Z", None)])
    assert clean.empty
    assert rejects["reason"].str.contains("tanpa prakiraan").all()


def test_bmkg_out_of_range_values_are_quarantined_and_missing_rain_is_not_imputed():
    clean, rejects = bmkg_frame([bmkg_env("2026-11-23T02:00:00Z", [
        bmkg_item("2026-11-23T03:00:00Z", hu=140),
        bmkg_item("2026-11-23T06:00:00Z", tp=None),
    ])])
    assert len(clean) == 1 and math.isnan(clean.loc[0, "precip_mm"])
    assert len(rejects) == 1 and "humidity_pct" in rejects.loc[0, "reason"]


def test_bmkg_failed_fetch_is_reported():
    clean, rejects = bmkg_frame([bmkg_env("2026-11-23T02:00:00Z", None, error="HTTP 500")])
    assert clean.empty
    assert rejects.loc[0, "reason"] == "fetch_failed: HTTP 500"


def om_env(fetched_at, hourly, error=None):
    return {"source": "open-meteo", "location": "bogor", "fetched_at": fetched_at, "status": 200, "error": error,
            "payload": None if error else {"hourly": hourly}}


def test_openmeteo_wide_arrays_become_one_row_per_hour():
    hourly = {"time": ["2026-11-23T00:00", "2026-11-23T01:00", "2026-11-23T02:00"],
              "precipitation": [0.0, -1.0, None], "relative_humidity_2m": [80, 81, 82]}
    clean, rejects = openmeteo_frame([om_env("2026-11-23T02:48:59Z", hourly)])
    assert len(clean) == 2  # jam dengan hujan negatif masuk karantina
    assert str(clean["valid_at"].dt.tz) == "UTC"
    assert clean["issued_at"].nunique() == 1
    assert math.isnan(clean.loc[1, "precip_mm"])  # kosong tetap kosong
    assert "precip_mm" in rejects.loc[0, "reason"]


def test_raw_payload_frame_keeps_failed_envelopes():
    df = raw_payload_frame([om_env("2026-11-23T02:48:59Z", {}, error="ReadTimeout")])
    assert df.loc[0, "error"] == "ReadTimeout"
    assert df.loc[0, "payload"] == "null"


def era5_items(values):
    return [{"latitude": loc.lat, "longitude": loc.lon,
             "daily": {"time": ["2026-11-16", "2026-11-17", "2026-11-18"], "precipitation_sum": values}}
            for loc in PILOT_LOCATIONS]


def test_era5_days_not_yet_available_are_dropped_not_stored_empty():
    df = era5_items_frame(era5_items([8.7, 2.6, None]), PILOT_LOCATIONS, "era5")
    assert len(df) == 2 * len(PILOT_LOCATIONS)
    assert df["precip_mm"].notna().all()


def test_era5_location_order_mismatch_raises():
    items = era5_items([1.0, 2.0, 3.0])
    items[0], items[6] = items[6], items[0]  # Jakarta ↔ Medan
    with pytest.raises(ValueError, match="koordinat"):
        era5_items_frame(items, PILOT_LOCATIONS, "era5")


def test_read_envelopes_since_skips_older_date_folders(tmp_path):
    import json
    from datetime import date
    from pipeline.transform.forecast import read_envelopes
    for day in ("2026-11-20", "2026-11-25", "2026-11-26"):
        f = tmp_path / "bmkg" / day / "0000Z" / "jakarta.json"
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"day": day}))
    assert [e["day"] for e in read_envelopes(tmp_path, "bmkg", since=date(2026, 11, 25))] == ["2026-11-25", "2026-11-26"]
    assert len(read_envelopes(tmp_path, "bmkg")) == 3

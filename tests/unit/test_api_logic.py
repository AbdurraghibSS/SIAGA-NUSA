from datetime import datetime, timedelta, timezone

from api.logic import cell_center, local_iso, summarize

T0 = datetime(2026, 11, 23, 3, tzinfo=timezone.utc)  # 10.00 WIB


def hours(values):
    return [(T0 + timedelta(hours=i), v) for i, v in enumerate(values)]


def test_summarize_total_category_peak_and_rain_start():
    s = summarize(hours([0, 0.2, 0.6, 2.6, 1.0, None]), None)
    assert s["total_mm"] == 4.4
    assert s["category"] == "ringan"
    assert s["peak_at"] == T0 + timedelta(hours=3) and s["peak_mm"] == 2.6
    assert s["rain_start_at"] == T0 + timedelta(hours=2)  # jam pertama ≥0,5 mm
    assert s["previous_total_mm"] is None


def test_summarize_drizzle_below_half_mm_counts_as_no_rain():
    s = summarize(hours([0, 0, 0.1]), None)
    assert s["category"] == "tidak hujan"
    assert s["rain_start_at"] is None


def test_summarize_completely_dry_has_no_peak():
    s = summarize(hours([0, 0, 0]), None)
    assert s["peak_at"] is None and s["peak_mm"] == 0.0


def test_previous_run_is_compared_only_on_shared_hours():
    latest = hours([1, 2, 3])
    previous = {T0: 0.5, T0 + timedelta(hours=1): 4.0, T0 - timedelta(hours=1): 99.0}  # jam di luar jendela diabaikan
    s = summarize(latest, previous)
    assert s["previous_total_mm"] == 4.5
    assert s["previous_peak_at"] == T0 + timedelta(hours=1)


def test_local_iso_uses_location_timezone():
    assert local_iso(T0, "Asia/Jakarta") == "2026-11-23T10:00:00+07:00"
    assert local_iso(T0, "Asia/Makassar") == "2026-11-23T11:00:00+08:00"
    assert local_iso(None, "Asia/Jakarta") is None


def test_cell_center_matches_grid_cell_encoding():
    # clean.petabencana.grid_cell: round(lon / 0.05), round(lat / 0.05)
    assert cell_center("2137_-124") == (106.85, -6.2)

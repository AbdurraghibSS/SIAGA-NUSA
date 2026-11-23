from datetime import date

import pytest

from pipeline.rivers import RiverPoint
from pipeline.transform.rivers import glofas_items_frame

POINTS = (
    RiverPoint("a", "jakarta", "A", -6.225, 106.825, "sedang", ""),
    RiverPoint("b", "bogor", "B", -6.625, 106.775, "sedang", ""),
)


def item(lat, lon, times, values):
    return {"latitude": lat, "longitude": lon, "daily": {"time": times, "river_discharge": values}}


def test_flags_forecast_drops_nulls_and_quarantines_negative():
    items = [
        item(-6.2249985, 106.82501, ["2026-11-22", "2026-11-23", "2026-11-24"], [30.1, None, 41.0]),
        item(-6.625, 106.775, ["2026-11-22", "2026-11-23", "2026-11-24"], [5.0, -1.0, 6.0]),
    ]
    clean, rejects = glofas_items_frame(items, POINTS, today=date(2026, 11, 23))
    assert len(clean) == 4
    assert clean.set_index(["point", "date"]).loc[("a", date(2026, 11, 24)), "is_forecast"]
    assert not clean.set_index(["point", "date"]).loc[("a", date(2026, 11, 22)), "is_forecast"]
    assert list(rejects["reason"]) == ["debit negatif"]


def test_swapped_order_is_an_error():
    items = [item(-6.625, 106.775, ["2026-11-22"], [5.0]), item(-6.225, 106.825, ["2026-11-22"], [30.0])]
    with pytest.raises(ValueError, match="bukan a"):
        glofas_items_frame(items, POINTS, today=date(2026, 11, 23))


def test_wrong_count_is_an_error():
    with pytest.raises(ValueError):
        glofas_items_frame([item(-6.225, 106.825, [], [])], POINTS, today=date(2026, 11, 23))

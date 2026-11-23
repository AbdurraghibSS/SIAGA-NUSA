import pytest

from pipeline.risk import FORECAST_SCORE, WEIGHTS, flood_freq_score, level_for, percentile, risk_index, tail_score


def test_percentile_midrank_for_ties():
    # Separuh hari bernilai 0: hari tanpa hujan → persentil 0,25, bukan 0,5.
    assert percentile(0.0, [0, 0, 5, 10]) == 0.25
    assert percentile(10.0, [0, 0, 5, 10]) == 0.875
    assert percentile(99.0, [0, 0, 5, 10]) == 1.0


def test_percentile_missing():
    assert percentile(3.0, []) is None
    assert percentile(None, [1, 2]) is None


@pytest.mark.parametrize("p,expected", [(0.1, 0.0), (0.5, 0.0), (0.75, 0.5), (1.0, 1.0), (None, None)])
def test_tail_score(p, expected):
    assert tail_score(p) == expected


@pytest.mark.parametrize("score,level", [(0, "Rendah"), (39, "Rendah"), (40, "Sedang"), (69, "Sedang"), (70, "Tinggi")])
def test_level_thresholds(score, level):
    assert level_for(score) == level


def test_all_components_max_is_100():
    result = risk_index({k: 1.0 for k in WEIGHTS})
    assert result["score"] == 100 and result["level"] == "Tinggi"


def test_missing_component_reweights():
    # Tanpa flood_freq, bobot 0,30/0,25/0,25 dinormalkan jadi 0,375/0,3125/0,3125.
    result = risk_index({"rain_72h": 0.8, "forecast": 0.0, "river": 0.0, "flood_freq": None})
    assert result["score"] == 30  # 0,8 × 0,375
    assert set(result["weights"]) == {"rain_72h", "forecast", "river"}
    assert sum(result["weights"].values()) == pytest.approx(1.0)


def test_no_components_gives_no_score():
    assert risk_index({"rain_72h": None})["score"] is None


def test_rejects_out_of_range_and_unknown():
    with pytest.raises(ValueError):
        risk_index({"river": 1.5})
    with pytest.raises(ValueError):
        risk_index({"tide": 0.5})


def test_forecast_scores_cover_all_bmkg_categories():
    from pipeline.rainfall import bmkg_category
    for mm in (0, 5, 30, 70, 120, 200):
        assert (bmkg_category(mm) or "tidak hujan") in FORECAST_SCORE


@pytest.mark.parametrize("freq,expected", [(0.0, 0.0), (0.01, 0.05), (0.20, 1.0), (0.25, 1.0)])
def test_flood_freq_score(freq, expected):
    assert flood_freq_score(freq) == pytest.approx(expected)


def test_flood_freq_missing():
    assert flood_freq_score(None) is None

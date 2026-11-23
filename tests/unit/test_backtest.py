import numpy as np
import pandas as pd
import pytest

from pipeline.backtest import fit_nonneg_logreg, normalize, season_of, simplex_grid


def test_nonneg_logreg_recovers_signal_and_zeroes_harmful_feature():
    rng = np.random.default_rng(0)
    X = rng.uniform(0, 1, size=(4000, 3))
    # fitur 0 kuat, fitur 1 lemah, fitur 2 justru berkorelasi negatif
    z = -3 + 4 * X[:, 0] + 1 * X[:, 1] - 2 * X[:, 2]
    y = rng.uniform(size=4000) < 1 / (1 + np.exp(-z))
    _, w = fit_nonneg_logreg(X, y)
    assert (w >= 0).all()
    assert w[0] > w[1] > 0
    assert w[2] == pytest.approx(0, abs=1e-6)  # dipaksa 0, bukan negatif


def test_normalize_sums_to_one_and_handles_all_zero():
    assert sum(normalize(np.array([2.0, 1.0, 1.0])).values()) == pytest.approx(1)
    assert normalize(np.zeros(3)) == pytest.approx({"rain_72h": 1 / 3, "forecast": 1 / 3, "river": 1 / 3})


def test_simplex_grid_size_and_sums():
    grid = simplex_grid(0.05)
    assert len(grid) == 231
    assert all(sum(w.values()) == pytest.approx(1) for w in grid)


def test_season_of():
    s = season_of(pd.Series(pd.to_datetime(["2017-11-01", "2018-04-30", "2018-11-01"])))
    assert list(s) == [2017, 2017, 2018]

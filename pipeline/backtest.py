"""Backtest indeks risiko · data harian historis + evaluasi bobot (dipakai notebook 03).

Satu baris = satu hari musim hujan (Nov–Apr) di satu kota, dengan skor komponen
seperti yang dihitung API pada pukul 00 WIB hari itu:

- rain_72h  : jumlah hujan ERA5 3 hari sampai kemarin → persentil bulan → `tail_score`
- forecast  : hujan ERA5 hari itu → kategori BMKG → skor (proksi **prakiraan sempurna**,
              karena arsip prakiraan baru dikumpulkan sejak Nov 2026; hasilnya optimistis)
- river     : debit GloFAS maks(hari ini, besok) → persentil bulan → `tail_score`

Label: banyaknya laporan banjir warga (sudah disaring) di seluruh Jabodetabek hari itu.
"""

from collections.abc import Callable

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.metrics import average_precision_score, roc_auc_score
from sqlalchemy import text

from pipeline.rainfall import bmkg_category
from pipeline.risk import FORECAST_SCORE, tail_score
from pipeline.rivers import RIVER_POINTS

COMPONENTS = ("rain_72h", "forecast", "river")
RAINY_MONTHS = (11, 12, 1, 2, 3, 4)
FIRST_SEASON, LAST_SEASON = 2017, 2024  # musim 2017/18 … 2024/25 (lengkap)


def season_of(dates: pd.Series) -> pd.Series:
    """Musim hujan = tahun bulan November-nya (Nov 2017–Apr 2018 → 2017)."""
    return (dates - pd.DateOffset(months=10)).dt.year


def monthly_percentile(df: pd.DataFrame, col: str) -> pd.Series:
    """Persentil mid-rank per bulan kalender, sama seperti `pipeline.risk.percentile`."""
    return df.groupby(df["date"].dt.month)[col].transform(lambda s: (s.rank(method="average") - 0.5) / s.count())


def build_dataset(engine, city: str = "jakarta") -> pd.DataFrame:
    point = next(p.slug for p in RIVER_POINTS if p.location == city)
    with engine.connect() as conn:
        rain = pd.read_sql(text(
            "SELECT date, precip_mm::float AS p, precip_3d_mm::float AS p3 FROM v_obs_rolling WHERE location = :c"
        ), conn, params={"c": city}, parse_dates=["date"])
        river = pd.read_sql(text(
            "SELECT date, discharge_m3s::float AS q FROM river_daily WHERE point = :p AND NOT is_forecast"
        ), conn, params={"p": point}, parse_dates=["date"])
        floods = pd.read_sql(text("""
            SELECT (created_at AT TIME ZONE 'Asia/Jakarta')::date AS date, COUNT(*) AS n_reports
            FROM flood_reports WHERE exclusion_reason IS NULL GROUP BY 1
        """), conn, parse_dates=["date"])

    df = rain.merge(river, on="date", how="inner").sort_values("date").reset_index(drop=True)
    df["p3_prev"] = df["p3"].shift(1)                     # 72 jam sebelum 00 WIB hari itu
    df["q_today_tomorrow"] = df["q"].rolling(2).max().shift(-1)
    df = df.dropna(subset=["p3_prev", "q_today_tomorrow", "p"]).reset_index(drop=True)
    df["rain_pct"] = monthly_percentile(df, "p3_prev")
    df["river_pct"] = monthly_percentile(df, "q_today_tomorrow")
    df["rain_72h"] = df["rain_pct"].map(tail_score)
    df["forecast"] = df["p"].map(lambda mm: FORECAST_SCORE[bmkg_category(mm) or "tidak hujan"])
    df["river"] = df["river_pct"].map(tail_score)

    df = df.merge(floods, on="date", how="left").fillna({"n_reports": 0})
    df["n_reports"] = df["n_reports"].astype(int)
    df["season"] = season_of(df["date"])
    keep = df["date"].dt.month.isin(RAINY_MONTHS) & df["season"].between(FIRST_SEASON, LAST_SEASON)
    return df[keep].reset_index(drop=True)


def weighted_score(df: pd.DataFrame, weights: dict[str, float]) -> np.ndarray:
    """Skor linier Σ wᵢ·komponenᵢ (bobot tidak perlu berjumlah 1; peringkat yang penting)."""
    return sum(weights[c] * df[c].to_numpy() for c in COMPONENTS)


def fit_nonneg_logreg(X: np.ndarray, y: np.ndarray, l2: float = 1e-3) -> tuple[float, np.ndarray]:
    """Regresi logistik dengan koefisien **≥ 0** (intercept bebas), L-BFGS-B.

    Koefisien dipaksa positif supaya tetap terbaca sebagai bobot: komponen yang
    lebih tinggi tidak boleh menurunkan risiko. Kembalikan (intercept, koefisien).
    """
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    n, k = X.shape

    def loss(theta):
        b, w = theta[0], theta[1:]
        z = b + X @ w
        # log(1 + e^z) − y·z, stabil secara numerik
        ll = np.logaddexp(0, z) - y * z
        grad_z = 1 / (1 + np.exp(-z)) - y
        value = ll.mean() + l2 * (w @ w)
        grad = np.concatenate([[grad_z.mean()], X.T @ grad_z / n + 2 * l2 * w])
        return value, grad

    p = np.clip(y.mean(), 1e-6, 1 - 1e-6)
    theta0 = np.concatenate([[np.log(p / (1 - p))], np.zeros(k)])
    bounds = [(None, None)] + [(0, None)] * k
    res = minimize(loss, theta0, jac=True, method="L-BFGS-B", bounds=bounds)
    if not res.success:
        raise RuntimeError(f"optimasi gagal: {res.message}")
    return float(res.x[0]), res.x[1:]


def normalize(w: np.ndarray) -> dict[str, float]:
    total = float(np.sum(w))
    if total <= 0:
        return {c: 1 / len(COMPONENTS) for c in COMPONENTS}
    return {c: float(v) / total for c, v in zip(COMPONENTS, w)}


def metrics(y: np.ndarray, score: np.ndarray) -> dict[str, float]:
    return {"auc": float(roc_auc_score(y, score)), "ap": float(average_precision_score(y, score))}


def loso(df: pd.DataFrame, y: np.ndarray, scorer: Callable[[pd.DataFrame, np.ndarray], Callable[[pd.DataFrame], np.ndarray]]):
    """Leave-one-season-out: untuk tiap musim, `scorer(train_df, train_y)` → fungsi skor, dipakai di musim itu.

    Kembalikan (skor out-of-fold untuk semua baris, daftar info per fold).
    """
    oof = np.full(len(df), np.nan)
    folds = []
    for season in sorted(df["season"].unique()):
        test = (df["season"] == season).to_numpy()
        score_fn, info = scorer(df[~test], y[~test])
        oof[test] = score_fn(df[test])
        folds.append({"season": int(season), "n_events": int(y[test].sum()), **info})
    return oof, folds


def fixed_scorer(weights: dict[str, float]):
    """Bobot tetap (tidak belajar) dalam bentuk yang sama dengan scorer LOSO."""
    def scorer(train_df, train_y):
        return (lambda d: weighted_score(d, weights)), {f"w_{c}": weights[c] for c in COMPONENTS}
    return scorer


def logreg_scorer(l2: float = 1e-3):
    def scorer(train_df, train_y):
        _, w = fit_nonneg_logreg(train_df[list(COMPONENTS)].to_numpy(), train_y, l2=l2)
        wn = normalize(w)
        return (lambda d: weighted_score(d, wn)), {f"w_{c}": wn[c] for c in COMPONENTS}
    return scorer


def simplex_grid(step: float = 0.05) -> list[dict[str, float]]:
    """Semua kombinasi bobot 3 komponen yang berjumlah 1 dengan langkah `step`."""
    n = round(1 / step)
    return [{"rain_72h": i / n, "forecast": j / n, "river": (n - i - j) / n}
            for i in range(n + 1) for j in range(n + 1 - i)]


def season_bootstrap(df: pd.DataFrame, y: np.ndarray, score_a: np.ndarray, score_b: np.ndarray,
                     n_boot: int = 2000, seed: int = 42) -> np.ndarray:
    """Selisih AUC (b − a) dengan bootstrap **per musim** (musim di-resample utuh, bukan per hari,
    karena hari-hari dalam satu musim saling berkaitan)."""
    rng = np.random.default_rng(seed)
    seasons = df["season"].to_numpy()
    uniq = np.unique(seasons)
    idx_by = {s: np.flatnonzero(seasons == s) for s in uniq}
    out = []
    for _ in range(n_boot):
        idx = np.concatenate([idx_by[s] for s in rng.choice(uniq, size=len(uniq), replace=True)])
        if y[idx].min() == y[idx].max():
            continue
        out.append(roc_auc_score(y[idx], score_b[idx]) - roc_auc_score(y[idx], score_a[idx]))
    return np.array(out)

"""Indeks risiko banjir rule-based v1 · fungsi murni (dipakai API dan backtest).

Empat komponen (plan §6.3), masing-masing skor 0–1:

| komponen  | bobot | dari                                                                  |
|-----------|:-----:|-----------------------------------------------------------------------|
| rain_72h  | 0,30  | hujan 72 jam terakhir, persentil terhadap jumlah 3 hari ERA5 bulan yang sama |
| forecast  | 0,25  | kategori BMKG dari total prakiraan 24 jam ke depan                    |
| river     | 0,25  | debit GloFAS hari ini–besok, persentil terhadap riwayat bulan yang sama |
| flood_freq| 0,20  | proporsi hari musim hujan dengan laporan warga ≤5 km, penuh di 0,20  |

Penyesuaian terhadap plan: persentil diubah menjadi skor dengan `tail_score`, yaitu
hanya bagian **di atas median** yang menambah risiko (p ≤ 0,5 → 0, p = 1 → 1).
Tanpa ini hari biasa (persentil ±0,5) sudah mendapat setengah skor, dan hampir
semua hari jatuh di level Sedang.

Penyesuaian kedua: plan menulis "proporsi musim hujan dengan laporan banjir", tetapi
ukuran itu mentok di 8/8 musim untuk Jakarta maupun Bogor. Dipakai proporsi **hari**
musim hujan (Jakarta ±0,25, Bogor ±0,01), skor penuh di 0,20 (1 dari 5 hari).

Komponen yang datanya tidak ada (mis. laporan warga hanya tersedia di Jabodetabek)
dikeluarkan dan bobot sisanya dinormalkan ulang. Komponen yang dipakai dicatat.
Level sengaja tidak memakai Waspada/Siaga/Awas (istilah resmi BMKG/BPBD).
"""

from bisect import bisect_left, bisect_right
from collections.abc import Sequence

METHOD_VERSION = "risk-v1"

WEIGHTS: dict[str, float] = {"rain_72h": 0.30, "forecast": 0.25, "river": 0.25, "flood_freq": 0.20}

# Kategori hujan harian BMKG → skor komponen prakiraan (plan §6.3).
FORECAST_SCORE: dict[str, float] = {
    "tidak hujan": 0.0,
    "ringan": 0.0,
    "sedang": 0.3,
    "lebat": 0.6,
    "sangat lebat": 0.85,
    "ekstrem": 1.0,
}

LEVELS = ((70, "Tinggi"), (40, "Sedang"), (0, "Rendah"))

# Proporsi hari musim hujan berlaporan banjir yang sudah dianggap skor penuh.
FLOOD_FREQ_FULL = 0.20


def percentile(value: float, reference: Sequence[float]) -> float | None:
    """Persentil (0–1) `value` terhadap `reference` dengan *mid-rank*: nilai yang sama dihitung setengah.

    Mid-rank penting untuk hujan: di bulan kering banyak hari bernilai 0, dan hari tanpa
    hujan tidak boleh mendapat persentil tinggi hanya karena seri dengan semua nol itu.
    """
    if value is None or not reference:
        return None
    ref = sorted(reference)
    below = bisect_left(ref, value)
    equal = bisect_right(ref, value) - below
    return (below + 0.5 * equal) / len(ref)


def tail_score(p: float | None) -> float | None:
    """Persentil → skor: 0 sampai median, lalu naik linier sampai 1 di persentil 100."""
    if p is None:
        return None
    return max(0.0, min(1.0, (p - 0.5) / 0.5))


def flood_freq_score(freq: float | None) -> float | None:
    """Proporsi hari berlaporan banjir → skor 0–1 (linier, penuh di `FLOOD_FREQ_FULL`)."""
    if freq is None:
        return None
    return max(0.0, min(1.0, freq / FLOOD_FREQ_FULL))


def level_for(score: int) -> str:
    return next(name for threshold, name in LEVELS if score >= threshold)


def risk_index(components: dict[str, float | None]) -> dict:
    """Gabungkan skor komponen (0–1, None = tidak tersedia) → skor 0–100 dan level.

    Kalau tidak ada satu pun komponen, skor None (jangan menebak).
    """
    unknown = set(components) - set(WEIGHTS)
    if unknown:
        raise ValueError(f"komponen tidak dikenal: {sorted(unknown)}")
    used = {k: v for k, v in components.items() if v is not None}
    if not used:
        return {"score": None, "level": None, "weights": {}, "method_version": METHOD_VERSION}
    for name, value in used.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"skor {name} harus 0–1, bukan {value}")
    total_weight = sum(WEIGHTS[k] for k in used)
    weights = {k: WEIGHTS[k] / total_weight for k in used}
    score = round(100 * sum(weights[k] * v for k, v in used.items()))
    return {"score": score, "level": level_for(score), "weights": weights, "method_version": METHOD_VERSION}

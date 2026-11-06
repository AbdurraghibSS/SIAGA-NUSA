"""Pembersihan laporan PetaBencana: wilayah Jabodetabek dan penanda latihan/uji.

Semua laporan arsip berstatus `confirmed`, termasuk latihan (HKB, duta, kelas
kampus/sekolah, pelatihan BPBD) dan uji. Di Jabodetabek, ±53% laporan banjir
termasuk kategori ini, jadi status tidak bisa dipakai sebagai penyaring.

Tiga lapis penanda, diterapkan berurutan:
1. `partner_code == "tescode"`
2. Kata kunci latihan/uji di teks (`DRILL_PATTERN`)
3. Ledakan laporan: satu sel ±5 km dalam satu jam berisi ≥10 laporan dengan
   foto <50%, atau ≥25 laporan. Banjir besar sungguhan (1 Jan 2020,
   25 Feb 2020, 20 Feb 2021) paling banyak ±18 laporan per sel-jam.
Aturan ini heuristik; sisa kontaminasi masih mungkin ada.
"""

import json
from pathlib import Path

import pandas as pd

# Kode BPS kab/kota Jabodetabek
JABODETABEK_REGION_CODES = frozenset({
    "3101", "3171", "3172", "3173", "3174", "3175",  # DKI Jakarta
    "3201", "3271",  # Kab/Kota Bogor
    "3276",  # Depok
    "3603", "3671", "3674",  # Kab/Kota Tangerang, Tangerang Selatan
    "3216", "3275",  # Kab/Kota Bekasi
})
# Untuk laporan tanpa region_code. Kasar; PostGIS + poligon kecamatan menggantikannya.
JABODETABEK_BBOX = (106.45, -6.70, 107.20, -6.00)  # lon_min, lat_min, lon_max, lat_max

DRILL_PATTERN = (
    r"hkb|kesiapsiagaan|duta|trainer|trener|training|challenge|#?112[ _]|#112\b"
    r"|simulasi|latihan|drill|gladi|\b(?:test|testing|tes)\b|uji ?coba|percobaan"
    r"|youth4gotongroyong|dkrb"
)
# Nama sekolah sengaja tidak masuk pola: laporan nyata sering memakai sekolah sebagai
# patokan lokasi ("SDN 07 Duren Sawit mulai tergenang"). Sesi kelas ditangkap penanda ledakan.
TEST_PARTNER_CODES = frozenset({"tescode"})

CELL_DEG = 0.05  # ±5,5 km
BURST_MIN_REPORTS = 10
BURST_MAX_IMAGE_SHARE = 0.5
BURST_HARD_MIN_REPORTS = 25


def load_archive(directory: Path) -> pd.DataFrame:
    """Ratakan semua `archive_*.json` menjadi satu tabel, satu baris per laporan."""
    rows = []
    for path in sorted(Path(directory).glob("archive_*.json")):
        for feat in json.loads(path.read_text(encoding="utf-8"))["features"]:
            p = feat["properties"]
            tags = p.get("tags") or {}
            lon, lat = (feat.get("geometry") or {}).get("coordinates") or (None, None)
            rows.append({
                "pkey": p["pkey"],
                "created_at": p["created_at"],
                "source": p.get("source"),
                "status": p.get("status"),
                "disaster_type": p.get("disaster_type"),
                "flood_depth": (p.get("report_data") or {}).get("flood_depth"),
                "text": p.get("text"),
                "partner_code": p.get("partner_code"),
                "has_image": bool(p.get("image_url")),
                "district_id": tags.get("district_id"),
                "region_code": tags.get("region_code"),
                "local_area_id": tags.get("local_area_id"),
                "instance_region_code": tags.get("instance_region_code"),
                "lon": lon,
                "lat": lat,
            })
    df = pd.DataFrame(rows).drop_duplicates("pkey")
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df["created_at_wib"] = df["created_at"].dt.tz_convert("Asia/Jakarta")
    return df.reset_index(drop=True)


def in_jabodetabek(df: pd.DataFrame) -> pd.Series:
    lon_min, lat_min, lon_max, lat_max = JABODETABEK_BBOX
    in_bbox = df["lon"].between(lon_min, lon_max) & df["lat"].between(lat_min, lat_max)
    return df["region_code"].isin(JABODETABEK_REGION_CODES) | (df["region_code"].isna() & in_bbox)


def grid_cell(df: pd.DataFrame, deg: float = CELL_DEG) -> pd.Series:
    """Sel grid ±5 km sebagai pengganti kecamatan sampai poligon tersedia."""
    return (df["lon"] / deg).round().astype("Int64").astype(str) + "_" + (df["lat"] / deg).round().astype("Int64").astype(str)


def flag_test_partner(df: pd.DataFrame) -> pd.Series:
    return df["partner_code"].fillna("").str.lower().isin(TEST_PARTNER_CODES)


def flag_drill_text(df: pd.DataFrame) -> pd.Series:
    return df["text"].fillna("").str.lower().str.contains(DRILL_PATTERN, regex=True)


def flag_burst(df: pd.DataFrame) -> pd.Series:
    """Tandai laporan di sel-jam yang berisi ledakan laporan (lihat docstring modul)."""
    key = pd.DataFrame({"cell": grid_cell(df), "hour": df["created_at_wib"].dt.floor("h")}, index=df.index)
    grouped = key.assign(has_image=df["has_image"]).groupby(["cell", "hour"])["has_image"]
    n = grouped.transform("size")
    image_share = grouped.transform("mean")
    return ((n >= BURST_MIN_REPORTS) & (image_share < BURST_MAX_IMAGE_SHARE)) | (n >= BURST_HARD_MIN_REPORTS)


def clean_floods(df: pd.DataFrame, region: pd.Series | None = None) -> pd.DataFrame:
    """Laporan banjir di wilayah tertentu (default Jabodetabek) dengan kolom penanda.

    Ledakan dihitung setelah dua penanda pertama, supaya laporan latihan yang sudah
    dikenali tidak ikut menaikkan hitungan sel-jam.
    """
    region = in_jabodetabek(df) if region is None else region
    out = df[region & df["disaster_type"].eq("flood")].copy()
    out["is_test_partner"] = flag_test_partner(out)
    out["is_drill_text"] = flag_drill_text(out)
    out["is_burst"] = False
    rest = ~(out["is_test_partner"] | out["is_drill_text"])
    out.loc[rest, "is_burst"] = flag_burst(out[rest])
    out["is_excluded"] = out["is_test_partner"] | out["is_drill_text"] | out["is_burst"]
    out["cell"] = grid_cell(out)
    out["date"] = out["created_at_wib"].dt.date
    return out


def rainy_season(ts: pd.Series) -> pd.Series:
    """Musim hujan Nov–Apr, dilabeli tahun mulainya (Nov 2023–Apr 2024 → 2023). Mei–Okt → NA."""
    month, year = ts.dt.month, ts.dt.year
    return pd.Series(pd.NA, index=ts.index, dtype="Int64").mask(month >= 11, year).mask(month <= 4, year - 1)

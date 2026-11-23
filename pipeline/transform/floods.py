"""Arsip PetaBencana → tabel `flood_reports`.

Memakai pembersihan yang sudah ada (`pipeline.clean.petabencana`): filter
Jabodetabek + banjir, lalu tiga penanda latihan/uji. Laporan yang ditandai tetap
disimpan dengan `exclusion_reason`, supaya jumlah yang disaring bisa ditampilkan.
"""

from pathlib import Path

import pandas as pd

from pipeline.clean.petabencana import clean_floods, load_archive

COLUMNS = ["pkey", "created_at", "lon", "lat", "region_code", "flood_depth_cm", "text",
           "has_image", "source", "cell", "exclusion_reason"]


def flood_frame(archive_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Kembalikan (laporan banjir Jabodetabek, baris ditolak, jumlah laporan mentah)."""
    raw = load_archive(archive_dir)
    no_coord = raw["lon"].isna() | raw["lat"].isna()
    rejects = raw[no_coord][["pkey", "created_at"]].assign(reason="tanpa koordinat")
    floods = clean_floods(raw[~no_coord])

    reason = pd.Series(pd.NA, index=floods.index, dtype="string")
    reason = reason.mask(floods["is_burst"], "ledakan laporan")
    reason = reason.mask(floods["is_drill_text"], "teks latihan/uji")
    reason = reason.mask(floods["is_test_partner"], "partner uji (tescode)")

    out = floods.assign(
        exclusion_reason=reason,
        flood_depth_cm=pd.to_numeric(floods["flood_depth"], errors="coerce").round().astype("Int64"),
        pkey=pd.to_numeric(floods["pkey"], errors="coerce").astype("Int64"),
        text=floods["text"].astype("string").str.strip(),
    )
    bad_depth = out["flood_depth_cm"].notna() & ~out["flood_depth_cm"].between(0, 500)
    out.loc[bad_depth, "flood_depth_cm"] = pd.NA  # kedalaman mustahil → kosong, laporan tetap dipakai
    return out[COLUMNS].reset_index(drop=True), rejects, len(raw)

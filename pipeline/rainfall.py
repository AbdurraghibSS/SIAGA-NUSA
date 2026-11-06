"""Kategori intensitas hujan BMKG dan definisi label Model A.

Sumber kategori: "Tabel Intensitas Hujan, CH perhari" dalam surat Peringatan Dini
Cuaca dan Iklim BMKG (e.T/ME.01.02/164/KBB3/VII/2026, 10 Juli 2026). Definisi
"hujan lebat ≥50 mm/24 jam" sebelumnya tertulis di Perka BMKG KEP.009/2010, yang
dicabut oleh Peraturan BMKG No. 9/2022 (peraturan baru tidak mencantumkan angka).
"""

# (kategori, batas bawah inklusif mm/hari, batas atas eksklusif atau None)
BMKG_DAILY_CATEGORIES: tuple[tuple[str, float, float | None], ...] = (
    ("ringan", 0.5, 20.0),
    ("sedang", 20.0, 50.0),
    ("lebat", 50.0, 100.0),
    ("sangat lebat", 100.0, 150.0),
    ("ekstrem", 150.0, None),
)

# Label Model A: akumulasi hujan harian (WIB) ERA5 ≥ 20 mm, yaitu "sedang ke atas".
# Ambang 50 mm (lebat) tidak dipakai karena ERA5 (grid ±25 km) meratakan hujan
# konvektif: Jakarta hanya 7 hari ≥50 mm dalam 2017–2026. Lihat notebooks/02.
MODEL_A_THRESHOLD_MM = 20.0


def bmkg_category(mm: float) -> str | None:
    """Kategori BMKG untuk curah hujan harian; None kalau <0,5 mm (tidak hujan)."""
    for name, low, high in BMKG_DAILY_CATEGORIES:
        if mm >= low and (high is None or mm < high):
            return name
    return None

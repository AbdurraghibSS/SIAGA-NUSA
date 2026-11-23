"""Titik pantau debit sungai (GloFAS) · satu sel sungai per kota pilot.

GloFAS v4 memakai grid 0,05° (±5,5 km). Sungai kota yang kecil tidak selalu jatuh
di sel terdekat dari pusat kota, dan sel dengan debit terbesar di sekitarnya bisa
saja sungai lain. Karena itu sel dipilih manual dari grid 7×7 debit rata-rata
klimatologis (`river_discharge_mean`): ambil sel yang membentuk alur, yaitu debitnya
naik ke arah hilir, dan paling dekat dengan sungai yang dimaksud.

Besaran debit GloFAS untuk sungai kecil jauh di bawah debit terukur. Karena itu
indeks risiko memakai **persentil terhadap riwayat sel itu sendiri** (relatif),
bukan angka m³/s mentah. `confidence` mencatat seberapa yakin sel ini mewakili
sungai yang disebut. Nilainya diperiksa dengan korelasi debit terhadap hujan
ERA5 kota (lihat docs/data-processing.md).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiverPoint:
    slug: str
    location: str  # slug kota pilot
    river: str
    lat: float  # pusat sel GloFAS
    lon: float
    confidence: str  # tinggi | sedang | rendah
    note: str


RIVER_POINTS: tuple[RiverPoint, ...] = (
    RiverPoint("ciliwung-manggarai", "jakarta", "Ciliwung (Manggarai)", -6.225, 106.825, "sedang",
               "Sel terdekat dari Manggarai (3 km), debit klimatologis ±22 m³/s."),
    RiverPoint("cisadane-bogor", "bogor", "Cisadane (Bogor)", -6.625, 106.775, "sedang",
               "Alur 106,775° naik ke hilir 3→13 m³/s. Sel Ciliwung di Katulampa hanya ±1 m³/s, terlalu kecil."),
    RiverPoint("citarum-dayeuhkolot", "bandung", "Citarum (Dayeuhkolot)", -6.975, 107.575, "tinggi",
               "Alur ke barat 14→27→33 m³/s, setelah pertemuan Cisangkuy."),
    RiverPoint("garang-semarang", "semarang", "Kali Garang (hulu)", -6.975, 110.325, "rendah",
               "Debit kecil (±5 m³/s), alur di grid tidak menerus sampai muara."),
    RiverPoint("code-yogyakarta", "yogyakarta", "Kali Code / Winongo", -7.825, 110.375, "rendah",
               "Sungai kecil di tengah kota. Alur yang jelas di grid adalah Progo (110,225°), di luar kota."),
    RiverPoint("surabaya-wonokromo", "surabaya", "Kali Surabaya (Wonokromo)", -7.275, 112.725, "rendah",
               "Debit GloFAS ±6 m³/s. Sebagian besar aliran Brantas dirutekan ke Kali Porong."),
    RiverPoint("deli-medan", "medan", "Sungai Deli", 3.575, 98.675, "sedang",
               "Sel terdekat (±13 m³/s). Sel 129 m³/s di timur kota adalah sungai lain."),
    RiverPoint("jeneberang-makassar", "makassar", "Jeneberang", -5.175, 119.425, "rendah",
               "Debit GloFAS ±4 m³/s, jauh di bawah debit terukur Jeneberang."),
)

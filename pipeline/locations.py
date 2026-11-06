"""Lokasi pilot SIAGA NUSA · pilot locations.

Koordinat diambil dari titik kelurahan BMKG (adm4), sehingga BMKG dan
Open-Meteo merujuk ke titik yang sama.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Location:
    slug: str
    name: str
    adm4: str  # kode kelurahan Kemendagri, dipakai API BMKG
    lat: float
    lon: float


PILOT_LOCATIONS: tuple[Location, ...] = (
    Location("jakarta", "Jakarta (Kemayoran)", "31.71.03.1001", -6.1647, 106.8454),
    Location("bogor", "Bogor (Batu Tulis)", "32.71.01.1001", -6.6216, 106.8087),
    Location("bandung", "Bandung (Sukarasa)", "32.73.01.1001", -6.8742, 107.5854),
    Location("semarang", "Semarang (Miroto)", "33.74.01.1001", -6.9837, 110.4187),
    Location("yogyakarta", "Yogyakarta (Kricak)", "34.71.01.1001", -7.7736, 110.3572),
    Location("surabaya", "Surabaya (Karang Pilang)", "35.78.01.1001", -7.3406, 112.6899),
    Location("medan", "Medan (Pasar Baru)", "12.71.01.1001", 3.5840, 98.6847),
    Location("makassar", "Makassar (Bontorannu)", "73.71.01.1001", -5.1622, 119.4043),
)

"""Logika ringkasan prakiraan · fungsi murni, tanpa database (mudah dites)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from pipeline.rainfall import bmkg_category

# Jam pertama dengan hujan ≥ ambang ini dianggap "hujan mulai".
RAIN_START_MM_PER_HOUR = 0.5

TZ_ABBR = {"Asia/Jakarta": "WIB", "Asia/Makassar": "WITA", "Asia/Jayapura": "WIT"}

# Kode BPS kab/kota Jabodetabek → nama untuk tampilan.
REGION_NAMES = {
    "3101": "Kepulauan Seribu", "3171": "Jakarta Selatan", "3172": "Jakarta Timur", "3173": "Jakarta Pusat",
    "3174": "Jakarta Barat", "3175": "Jakarta Utara", "3201": "Kabupaten Bogor", "3271": "Kota Bogor",
    "3276": "Kota Depok", "3603": "Kabupaten Tangerang", "3671": "Kota Tangerang",
    "3674": "Kota Tangerang Selatan", "3216": "Kabupaten Bekasi", "3275": "Kota Bekasi",
}


def local_iso(ts: datetime | None, tz: str) -> str | None:
    """Datetime ber-zona → ISO 8601 di zona lokal lokasi, mis. 2026-11-23T19:00:00+07:00."""
    return ts.astimezone(ZoneInfo(tz)).isoformat() if ts else None


def peak(hours: list[tuple[datetime, float | None]]) -> tuple[datetime | None, float | None]:
    """Jam dengan hujan terbesar. (None, None) kalau tidak ada angka sama sekali."""
    values = [(t, v) for t, v in hours if v is not None]
    if not values or max(v for _, v in values) <= 0:
        return None, (0.0 if values else None)
    return max(values, key=lambda tv: tv[1])


def summarize(latest: list[tuple[datetime, float | None]], previous: dict[datetime, float | None] | None) -> dict:
    """Ringkas 24 jam prakiraan: total, kategori BMKG, puncak, jam mulai hujan, dan perubahan.

    `previous` dibandingkan hanya pada jam yang juga ada di run terbaru, supaya total
    kedua run dihitung atas jendela yang sama.
    """
    values = [v for _, v in latest if v is not None]
    total = round(sum(values), 1) if values else None
    peak_at, peak_mm = peak(latest)
    start = next((t for t, v in latest if v is not None and v >= RAIN_START_MM_PER_HOUR), None)

    prev_total = prev_peak_at = None
    if previous:
        shared = [(t, previous.get(t)) for t, _ in latest]
        prev_values = [v for _, v in shared if v is not None]
        if prev_values:
            prev_total = round(sum(prev_values), 1)
            prev_peak_at, _ = peak(shared)

    return {
        "total_mm": total,
        # bmkg_category() memberi None di bawah 0,5 mm; samakan dengan fungsi SQL bmkg_category().
        "category": (bmkg_category(total) or "tidak hujan") if total is not None else None,
        "peak_at": peak_at,
        "peak_mm": peak_mm,
        "rain_start_at": start,
        "previous_total_mm": prev_total,
        "previous_peak_at": prev_peak_at,
    }


def cell_center(cell: str, deg: float = 0.05) -> tuple[float, float]:
    """Kode sel `"<lon_idx>_<lat_idx>"` (lihat clean.petabencana.grid_cell) → (lon, lat) pusat sel."""
    lon_idx, lat_idx = cell.split("_")
    return round(int(lon_idx) * deg, 4), round(int(lat_idx) * deg, 4)

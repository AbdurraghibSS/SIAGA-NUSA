"""Model respons API (Pydantic) · kontrak data untuk frontend dan, nanti, tool agen.

Semua waktu dikirim sebagai ISO 8601 di zona lokal lokasi (WIB/WITA), supaya
frontend tidak perlu menebak zona waktu.
"""

from pydantic import BaseModel, Field


class CitySummary(BaseModel):
    slug: str
    city: str
    tz_abbr: str
    issued_at: str | None = Field(description="Waktu run Open-Meteo terbaru (diambil)")
    total_24h_mm: float | None
    category: str | None = Field(description="Kategori hujan harian BMKG dari total 24 jam")
    peak_at: str | None
    peak_mm: float | None


class HourValue(BaseModel):
    valid_at: str
    precip_mm: float | None
    precip_prob_pct: float | None = None


class ForecastRun(BaseModel):
    issued_at: str
    hours: list[HourValue]


class ForecastSummary(BaseModel):
    total_mm: float | None
    category: str | None
    peak_at: str | None
    peak_mm: float | None
    rain_start_at: str | None
    previous_total_mm: float | None
    previous_peak_at: str | None


class BmkgBlock(BaseModel):
    valid_at: str
    weather_desc: str | None
    precip_mm: float | None
    temperature_c: float | None


class BmkgForecast(BaseModel):
    area: str
    analysis_at: str
    first_fetched_at: str
    blocks: list[BmkgBlock]


class Forecast(BaseModel):
    slug: str
    city: str
    tz_abbr: str
    window_start: str
    latest: ForecastRun | None
    previous: ForecastRun | None
    summary: ForecastSummary | None
    bmkg: BmkgForecast | None


class SourceStatus(BaseModel):
    source: str
    last_fetched_at: str | None
    last_ok_at: str | None
    n_locations_ok_last: int
    n_locations: int
    n_failed_24h: int


class JobStatus(BaseModel):
    job: str
    status: str
    started_at: str
    finished_at: str | None
    rows_read: int
    rows_loaded: int
    rows_rejected: int
    detail: str | None


class QuarantineCount(BaseModel):
    job: str
    reason: str
    n: int


class DataRanges(BaseModel):
    era5_last_date: str | None
    flood_last_report_at: str | None
    flood_reports_used: int
    flood_reports_excluded: int


class Status(BaseModel):
    checked_at: str
    sources: list[SourceStatus]
    jobs: list[JobStatus]
    quarantine: list[QuarantineCount]
    ranges: DataRanges


class FloodCell(BaseModel):
    lon: float
    lat: float
    n: int


class FloodRegion(BaseModel):
    region_code: str | None
    name: str
    n: int


class FloodReport(BaseModel):
    created_at: str
    lon: float
    lat: float
    region: str
    flood_depth_cm: int | None
    text: str | None


class FloodSummary(BaseModel):
    window_days: int
    latest_report_at: str | None
    n_used: int
    n_excluded: int
    n_last_7d: int
    cells: list[FloodCell]
    regions: list[FloodRegion]
    recent: list[FloodReport]


class DailyRain(BaseModel):
    date: str
    precip_mm: float | None
    precip_3d_mm: float | None
    precip_7d_mm: float | None
    category: str | None


class RainHistory(BaseModel):
    slug: str
    city: str
    days: list[DailyRain]


class MapCity(BaseModel):
    slug: str
    city: str
    tz_abbr: str
    lat: float
    lon: float
    issued_at: str | None
    total_24h_mm: float | None
    category: str | None
    hours: list[HourValue]
    bmkg_now: str | None = Field(description="Cuaca BMKG untuk blok 3 jam yang sedang berjalan")


class WeatherMap(BaseModel):
    window_start: str = Field(description="Jam pertama slider, WIB")
    cities: list[MapCity]

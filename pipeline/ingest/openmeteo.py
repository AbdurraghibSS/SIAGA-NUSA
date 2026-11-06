"""Open-Meteo Forecast, prakiraan per jam untuk semua lokasi dalam satu panggilan.

Respons tidak memuat waktu terbit, jadi `fetched_at` di envelope menjadi
penanda versinya. Lisensi CC BY 4.0, 10.000 panggilan/hari.
"""

from pipeline.locations import Location

SOURCE = "open-meteo"
URL = "https://api.open-meteo.com/v1/forecast"
HOURLY = (
    "precipitation",
    "rain",
    "precipitation_probability",
    "temperature_2m",
    "relative_humidity_2m",
    "pressure_msl",
    "wind_speed_10m",
    "wind_direction_10m",
    "cloud_cover",
)
FORECAST_DAYS = 7


def params_for(locations: tuple[Location, ...]) -> dict[str, str]:
    return {
        "latitude": ",".join(str(loc.lat) for loc in locations),
        "longitude": ",".join(str(loc.lon) for loc in locations),
        "hourly": ",".join(HOURLY),
        "forecast_days": str(FORECAST_DAYS),
        "timezone": "UTC",
    }


def split(payload: dict | list, locations: tuple[Location, ...]) -> list[dict]:
    """Satu lokasi → dict, beberapa lokasi → list, urutannya sama dengan permintaan."""
    items = payload if isinstance(payload, list) else [payload]
    if len(items) != len(locations):
        raise ValueError(f"expected {len(locations)} locations, got {len(items)}")
    return items

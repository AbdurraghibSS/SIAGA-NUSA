"""API SIAGA NUSA (FastAPI) · menyajikan data pipeline ke dasbor, dan nanti ke agen.

    uvicorn api.main:app --reload --port 8010
    → dasbor  http://localhost:8010/
    → dokumentasi interaktif  http://localhost:8010/docs

Pola sesi 10 & 11: model respons Pydantic, endpoint publik read-only, dan endpoint
admin yang dilindungi header `X-API-Key`.
"""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from api.logic import REGION_NAMES, TZ_ABBR, cell_center, local_iso, summarize
from api.schemas import (BmkgBlock, BmkgForecast, CitySummary, DailyRain, DataRanges, FloodCell, FloodRegion,
                         FloodReport, FloodSummary, Forecast, ForecastRun, ForecastSummary, HourValue, JobStatus,
                         MapCity, QuarantineCount, RainHistory, RiskComponent, RiskOverview, RiverDay, RiverSeries,
                         SourceStatus, Status, WeatherMap, CityRisk)
from pipeline.config import REPO_ROOT, settings
from pipeline.db import engine
from pipeline.locations import PILOT_LOCATIONS
from pipeline.rainfall import bmkg_category
from pipeline.risk import FORECAST_SCORE, flood_freq_score, percentile, risk_index, tail_score
from pipeline.rivers import RIVER_POINTS

log = logging.getLogger(__name__)
LOCATIONS = {loc.slug: loc for loc in PILOT_LOCATIONS}
RIVERS = {p.location: p for p in RIVER_POINTS}
MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
RAIN_MIN_HOURS = 60  # hujan 72 jam dianggap ada kalau ≥60 jam tercakup run Open-Meteo
WINDOW_HOURS = 24

app = FastAPI(
    title="SIAGA NUSA API",
    description="Cuaca dan risiko banjir dari data BMKG, Open-Meteo, dan PetaBencana. Bukan sistem peringatan dini resmi.",
    version="0.2.0",
)


def _window_start() -> datetime:
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _location(slug: str):
    loc = LOCATIONS.get(slug)
    if loc is None:
        raise HTTPException(status_code=404, detail=f"Lokasi '{slug}' tidak ada. Pilihan: {', '.join(LOCATIONS)}")
    return loc


# ---------------------------------------------------------------------------
# Publik
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Publik"])
def health() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception as exc:  # health check tidak boleh melempar
        raise HTTPException(status_code=503, detail=f"database: {type(exc).__name__}")


def _latest_runs(conn, slug: str) -> list[datetime]:
    return list(conn.execute(text(
        "SELECT issued_at FROM v_hourly_runs WHERE location = :loc AND run_rank <= 2 ORDER BY run_rank"
    ), {"loc": slug}).scalars())


def _hours(conn, slug: str, issued_at: datetime, start: datetime) -> list[tuple[datetime, float | None, float | None]]:
    rows = conn.execute(text("""
        SELECT valid_at, precip_mm, precip_prob_pct FROM forecast_hourly
        WHERE location = :loc AND issued_at = :issued AND valid_at >= :start AND valid_at < :end
        ORDER BY valid_at
    """), {"loc": slug, "issued": issued_at, "start": start, "end": start + timedelta(hours=WINDOW_HOURS)})
    return [(r.valid_at, r.precip_mm, r.precip_prob_pct) for r in rows]


@app.get("/api/cities", response_model=list[CitySummary], tags=["Prakiraan"])
def cities() -> list[CitySummary]:
    """Total hujan 24 jam ke depan per kota pilot, dari run Open-Meteo terbaru."""
    start = _window_start()
    out = []
    with engine.connect() as conn:
        for loc in PILOT_LOCATIONS:
            runs = _latest_runs(conn, loc.slug)
            if not runs:
                out.append(CitySummary(slug=loc.slug, city=loc.city, tz_abbr=TZ_ABBR[loc.tz], issued_at=None,
                                       total_24h_mm=None, category=None, peak_at=None, peak_mm=None))
                continue
            hours = _hours(conn, loc.slug, runs[0], start)
            s = summarize([(t, p) for t, p, _ in hours], None)
            out.append(CitySummary(
                slug=loc.slug, city=loc.city, tz_abbr=TZ_ABBR[loc.tz], issued_at=local_iso(runs[0], loc.tz),
                total_24h_mm=s["total_mm"], category=s["category"],
                peak_at=local_iso(s["peak_at"], loc.tz), peak_mm=s["peak_mm"],
            ))
    return out


@app.get("/api/forecast/{slug}", response_model=Forecast, tags=["Prakiraan"])
def forecast(slug: str) -> Forecast:
    """Prakiraan per jam 24 jam ke depan: run terbaru vs sebelumnya, plus prakiraan resmi BMKG per 3 jam."""
    loc = _location(slug)
    start = _window_start()
    iso = lambda ts: local_iso(ts, loc.tz)  # noqa: E731
    with engine.connect() as conn:
        runs = _latest_runs(conn, slug)
        latest = previous = summary = None
        if runs:
            lat_hours = _hours(conn, slug, runs[0], start)
            latest = ForecastRun(issued_at=iso(runs[0]), hours=[
                HourValue(valid_at=iso(t), precip_mm=p, precip_prob_pct=pr) for t, p, pr in lat_hours])
            prev_map = None
            if len(runs) > 1:
                prev_hours = _hours(conn, slug, runs[1], start)
                prev_map = {t: p for t, p, _ in prev_hours}
                previous = ForecastRun(issued_at=iso(runs[1]), hours=[
                    HourValue(valid_at=iso(t), precip_mm=p, precip_prob_pct=pr) for t, p, pr in prev_hours])
            s = summarize([(t, p) for t, p, _ in lat_hours], prev_map)
            summary = ForecastSummary(**{k: iso(v) if isinstance(v, datetime) else v for k, v in s.items()})

        # BMKG: blok 3 jam yang beririsan dengan jendela (blok yang sedang berjalan ikut).
        rows = conn.execute(text("""
            SELECT analysis_at, first_fetched_at, valid_at, weather_desc, precip_mm, temperature_c
            FROM v_bmkg_latest
            WHERE location = :loc AND valid_at > :start - INTERVAL '3 hours' AND valid_at < :end
            ORDER BY valid_at
        """), {"loc": slug, "start": start, "end": start + timedelta(hours=WINDOW_HOURS)}).all()
        bmkg = None
        if rows:
            bmkg = BmkgForecast(
                area=loc.name.split("(")[-1].rstrip(")"),
                analysis_at=iso(rows[0].analysis_at), first_fetched_at=iso(rows[0].first_fetched_at),
                blocks=[BmkgBlock(valid_at=iso(r.valid_at), weather_desc=r.weather_desc, precip_mm=r.precip_mm,
                                  temperature_c=r.temperature_c) for r in rows],
            )
    return Forecast(slug=slug, city=loc.city, tz_abbr=TZ_ABBR[loc.tz], window_start=iso(start),
                    latest=latest, previous=previous, summary=summary, bmkg=bmkg)


@app.get("/api/map", response_model=WeatherMap, tags=["Prakiraan"])
def weather_map() -> WeatherMap:
    """Semua kota pilot dengan hujan per jam 24 jam ke depan (untuk animasi peta), satu panggilan."""
    start = _window_start()
    out = []
    with engine.connect() as conn:
        for loc in PILOT_LOCATIONS:
            iso = lambda ts, tz=loc.tz: local_iso(ts, tz)  # noqa: E731
            runs = _latest_runs(conn, loc.slug)
            hours = _hours(conn, loc.slug, runs[0], start) if runs else []
            s = summarize([(t, p) for t, p, _ in hours], None) if hours else {"total_mm": None, "category": None}
            now = conn.execute(text("""
                SELECT weather_desc FROM v_bmkg_latest
                WHERE location = :loc AND valid_at <= :t ORDER BY valid_at DESC LIMIT 1
            """), {"loc": loc.slug, "t": start}).scalar()
            out.append(MapCity(
                slug=loc.slug, city=loc.city, tz_abbr=TZ_ABBR[loc.tz], lat=loc.lat, lon=loc.lon,
                issued_at=iso(runs[0]) if runs else None, total_24h_mm=s["total_mm"], category=s["category"],
                hours=[HourValue(valid_at=iso(t), precip_mm=p, precip_prob_pct=pr) for t, p, pr in hours],
                bmkg_now=now,
            ))
    return WeatherMap(window_start=local_iso(start, "Asia/Jakarta"), cities=out)


@app.get("/api/history/{slug}", response_model=RainHistory, tags=["Prakiraan"])
def history(slug: str, days: int = Query(30, ge=1, le=3650)) -> RainHistory:
    """Hujan harian ERA5 (reanalysis, tertinggal ±5 hari) dengan akumulasi 3 dan 7 hari."""
    loc = _location(slug)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT date, precip_mm, precip_3d_mm, precip_7d_mm, category FROM v_obs_rolling
            WHERE location = :loc ORDER BY date DESC LIMIT :n
        """), {"loc": slug, "n": days}).all()
    return RainHistory(slug=slug, city=loc.city, days=[
        DailyRain(date=r.date.isoformat(), precip_mm=r.precip_mm, precip_3d_mm=r.precip_3d_mm,
                  precip_7d_mm=r.precip_7d_mm, category=r.category) for r in reversed(rows)])


@app.get("/api/floods", response_model=FloodSummary, tags=["Banjir"])
def floods(days: int = Query(365, ge=1, le=3650), recent: int = Query(12, ge=0, le=100)) -> FloodSummary:
    """Laporan banjir warga Jabodetabek (PetaBencana, belum terverifikasi). Laporan latihan/uji tidak dihitung."""
    tz = "Asia/Jakarta"
    with engine.connect() as conn:
        latest_at = conn.execute(text("SELECT MAX(created_at) FROM flood_reports WHERE exclusion_reason IS NULL")).scalar()
        params = {"since": datetime.now(timezone.utc) - timedelta(days=days)}
        counts = conn.execute(text("""
            SELECT COUNT(*) FILTER (WHERE exclusion_reason IS NULL)     AS used,
                   COUNT(*) FILTER (WHERE exclusion_reason IS NOT NULL) AS excluded,
                   COUNT(*) FILTER (WHERE exclusion_reason IS NULL AND created_at > NOW() - INTERVAL '7 days') AS last7
            FROM flood_reports WHERE created_at >= :since
        """), params).one()
        cells = conn.execute(text("""
            SELECT cell, COUNT(*) AS n FROM flood_reports
            WHERE exclusion_reason IS NULL AND created_at >= :since GROUP BY cell
        """), params).all()
        regions = conn.execute(text("""
            SELECT region_code, COUNT(*) AS n FROM flood_reports
            WHERE exclusion_reason IS NULL AND created_at >= :since
            GROUP BY region_code ORDER BY n DESC
        """), params).all()
        items = conn.execute(text("""
            SELECT created_at, lon, lat, region_code, flood_depth_cm, text FROM flood_reports
            WHERE exclusion_reason IS NULL ORDER BY created_at DESC LIMIT :n
        """), {"n": recent}).all()
    region_name = lambda code: REGION_NAMES.get(code or "", "Tanpa kode wilayah")  # noqa: E731
    return FloodSummary(
        window_days=days, latest_report_at=local_iso(latest_at, tz),
        n_used=counts.used, n_excluded=counts.excluded, n_last_7d=counts.last7,
        cells=[FloodCell(lon=lon, lat=lat, n=r.n) for r in cells for lon, lat in [cell_center(r.cell)]],
        regions=[FloodRegion(region_code=r.region_code, name=region_name(r.region_code), n=r.n) for r in regions],
        recent=[FloodReport(created_at=local_iso(r.created_at, tz), lon=r.lon, lat=r.lat,
                            region=region_name(r.region_code), flood_depth_cm=r.flood_depth_cm,
                            text=(r.text or "")[:280] or None) for r in items],
    )


# ---------------------------------------------------------------------------
# Indeks risiko banjir (rule-based v1, lihat pipeline/risk.py)
# ---------------------------------------------------------------------------
def _fmt(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def _city_risk(conn, loc, start: datetime, month: int) -> CityRisk:
    mon = MONTHS[month]
    comps: list[RiskComponent] = []

    # 1. Hujan 72 jam terakhir (estimasi model) vs jumlah 3 hari ERA5 bulan yang sama.
    rain = conn.execute(text("""
        SELECT COUNT(precip_mm) AS n, SUM(precip_mm) AS mm FROM v_rain_recent_est
        WHERE location = :loc AND valid_at >= :start - INTERVAL '72 hours' AND valid_at < :start
    """), {"loc": loc.slug, "start": start}).one()
    ref = conn.execute(text("""
        SELECT precip_3d_mm::float FROM v_obs_rolling
        WHERE location = :loc AND EXTRACT(MONTH FROM date) = :m AND precip_3d_mm IS NOT NULL
    """), {"loc": loc.slug, "m": month}).scalars().all()
    if rain.n >= RAIN_MIN_HOURS and ref:
        mm = round(float(rain.mm), 1)
        p = percentile(mm, ref)
        comps.append(RiskComponent(
            key="rain_72h", label="Hujan 72 jam terakhir", source="DATA MODEL CUACA", available=True,
            score=tail_score(p), weight=None, value=mm, unit="mm", percentile=round(p, 3),
            detail=f"{_fmt(mm)} mm (estimasi model), persentil {round(p * 100)} untuk 3 hari di bulan {mon}"))
    else:
        comps.append(RiskComponent(
            key="rain_72h", label="Hujan 72 jam terakhir", source="DATA MODEL CUACA", available=False, score=None,
            weight=None, value=None, unit="mm", percentile=None,
            detail=f"Hanya {rain.n} dari 72 jam tercakup snapshot prakiraan"))

    # 2. Prakiraan 24 jam ke depan (run Open-Meteo terbaru) → kategori BMKG.
    runs = _latest_runs(conn, loc.slug)
    hours = _hours(conn, loc.slug, runs[0], start) if runs else []
    total = summarize([(t, p) for t, p, _ in hours], None)["total_mm"] if hours else None
    if total is not None:
        cat = bmkg_category(total) or "tidak hujan"
        comps.append(RiskComponent(
            key="forecast", label="Prakiraan 24 jam", source="DATA MODEL CUACA", available=True,
            score=FORECAST_SCORE[cat], weight=None, value=total, unit="mm", percentile=None,
            detail=f"{_fmt(total)} mm, kategori {cat} (skala harian BMKG)"))
    else:
        comps.append(RiskComponent(
            key="forecast", label="Prakiraan 24 jam", source="DATA MODEL CUACA", available=False, score=None,
            weight=None, value=None, unit="mm", percentile=None, detail="Belum ada run Open-Meteo"))

    # 3. Debit sungai: maksimum hari ini–besok (UTC) vs riwayat bulan yang sama.
    river = RIVERS.get(loc.slug)
    q = None
    if river:
        q = conn.execute(text("""
            SELECT MAX(discharge_m3s) FROM river_daily
            WHERE point = :pt AND date BETWEEN :d AND :d + 1
        """), {"pt": river.slug, "d": start.date()}).scalar()
    if q is not None:
        ref = conn.execute(text("""
            SELECT discharge_m3s::float FROM river_daily
            WHERE point = :pt AND NOT is_forecast AND EXTRACT(MONTH FROM date) = :m
        """), {"pt": river.slug, "m": month}).scalars().all()
        p = percentile(q, ref)
        comps.append(RiskComponent(
            key="river", label=f"Debit {river.river}", source="DATA MODEL CUACA", available=p is not None,
            score=tail_score(p), weight=None, value=round(q, 1), unit="m³/s",
            percentile=round(p, 3) if p is not None else None,
            detail=f"{_fmt(q)} m³/s hari ini–besok (GloFAS), persentil {round(p * 100)} untuk bulan {mon}"
                   if p is not None else "Riwayat debit belum ada"))
    else:
        comps.append(RiskComponent(
            key="river", label="Debit sungai", source="DATA MODEL CUACA", available=False, score=None, weight=None,
            value=None, unit="m³/s", percentile=None, detail="Data debit GloFAS belum dimuat"))

    # 4. Frekuensi banjir historis (hanya di cakupan laporan PetaBencana).
    ff = conn.execute(text("SELECT flood_days, season_days, freq::float AS freq FROM v_flood_season_freq WHERE location = :loc"),
                      {"loc": loc.slug}).one_or_none()
    if ff:
        comps.append(RiskComponent(
            key="flood_freq", label="Riwayat laporan banjir", source="LAPORAN WARGA", available=True,
            score=flood_freq_score(ff.freq), weight=None, value=round(ff.freq, 4), unit="proporsi hari",
            percentile=None,
            detail=f"{ff.flood_days} dari {ff.season_days} hari musim hujan 2017–2025 ada laporan ≤5 km"))
    else:
        comps.append(RiskComponent(
            key="flood_freq", label="Riwayat laporan banjir", source="LAPORAN WARGA", available=False, score=None,
            weight=None, value=None, unit="proporsi hari", percentile=None,
            detail="Laporan warga PetaBencana baru dikumpulkan untuk Jabodetabek"))

    result = risk_index({c.key: c.score for c in comps})
    for c in comps:
        c.weight = round(result["weights"].get(c.key), 3) if c.key in result["weights"] else None
    return CityRisk(slug=loc.slug, city=loc.city, score=result["score"], level=result["level"],
                    method_version=result["method_version"], components=comps)


@app.get("/api/risk", response_model=RiskOverview, tags=["Risiko"])
def risk() -> RiskOverview:
    """Indeks risiko banjir rule-based (0–100, Rendah/Sedang/Tinggi) per kota, dengan rincian komponen."""
    start = _window_start()
    month = datetime.now(ZoneInfo("Asia/Jakarta")).month
    with engine.connect() as conn:
        cities = [_city_risk(conn, loc, start, month) for loc in PILOT_LOCATIONS]
    return RiskOverview(computed_at=local_iso(datetime.now(timezone.utc), "Asia/Jakarta"), month=month, cities=cities)


@app.get("/api/river/{slug}", response_model=RiverSeries, tags=["Risiko"])
def river(slug: str, days: int = Query(60, ge=7, le=3650)) -> RiverSeries:
    """Debit harian GloFAS titik sungai kota: riwayat `days` hari + prakiraan, dengan median & p90 bulan ini."""
    loc = _location(slug)
    pt = RIVERS[slug]
    month = datetime.now(ZoneInfo("Asia/Jakarta")).month
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT date, discharge_m3s, is_forecast FROM river_daily
            WHERE point = :pt AND date > CURRENT_DATE - :n ORDER BY date
        """), {"pt": pt.slug, "n": days}).all()
        q = conn.execute(text("""
            SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY discharge_m3s) AS p50,
                   percentile_cont(0.9) WITHIN GROUP (ORDER BY discharge_m3s) AS p90
            FROM river_daily WHERE point = :pt AND NOT is_forecast AND EXTRACT(MONTH FROM date) = :m
        """), {"pt": pt.slug, "m": month}).one()
    r1 = lambda x: round(x, 1) if x is not None else None  # noqa: E731
    return RiverSeries(slug=slug, city=loc.city, point=pt.slug, river=pt.river, lat=pt.lat, lon=pt.lon,
                       confidence=pt.confidence, note=pt.note, month_p50_m3s=r1(q.p50), month_p90_m3s=r1(q.p90),
                       days=[RiverDay(date=r.date.isoformat(), discharge_m3s=round(r.discharge_m3s, 2),
                                      is_forecast=r.is_forecast) for r in rows])


@app.get("/api/status", response_model=Status, tags=["Status"])
def status() -> Status:
    """Kesegaran tiap sumber, job pipeline terakhir, dan isi karantina."""
    tz = "Asia/Jakarta"
    with engine.connect() as conn:
        sources = conn.execute(text("SELECT * FROM v_source_freshness ORDER BY source")).all()
        jobs = conn.execute(text("""
            SELECT DISTINCT ON (job) job, status, started_at, finished_at, rows_read, rows_loaded, rows_rejected, detail
            FROM ingest_runs ORDER BY job, started_at DESC
        """)).all()
        quarantine = conn.execute(text(
            "SELECT job, reason, COUNT(*) AS n FROM quarantine GROUP BY job, reason ORDER BY job, n DESC")).all()
        era5_last = conn.execute(text("SELECT MAX(date) FROM obs_daily WHERE dataset = 'era5'")).scalar()
        river_last = conn.execute(text("SELECT MAX(date) FROM river_daily WHERE NOT is_forecast")).scalar()
        fl = conn.execute(text("""
            SELECT MAX(created_at) FILTER (WHERE exclusion_reason IS NULL) AS last_at,
                   COUNT(*) FILTER (WHERE exclusion_reason IS NULL) AS used,
                   COUNT(*) FILTER (WHERE exclusion_reason IS NOT NULL) AS excluded
            FROM flood_reports
        """)).one()
    return Status(
        checked_at=local_iso(datetime.now(timezone.utc), tz),
        sources=[SourceStatus(source=s.source, last_fetched_at=local_iso(s.last_fetched_at, tz),
                              last_ok_at=local_iso(s.last_ok_at, tz), n_locations_ok_last=s.n_locations_ok_last,
                              n_locations=s.n_locations, n_failed_24h=s.n_failed_24h) for s in sources],
        jobs=[JobStatus(job=j.job, status=j.status, started_at=local_iso(j.started_at, tz),
                        finished_at=local_iso(j.finished_at, tz), rows_read=j.rows_read, rows_loaded=j.rows_loaded,
                        rows_rejected=j.rows_rejected, detail=j.detail) for j in jobs],
        quarantine=[QuarantineCount(job=q.job, reason=q.reason[:160], n=q.n) for q in quarantine],
        ranges=DataRanges(era5_last_date=era5_last.isoformat() if era5_last else None,
                          river_last_date=river_last.isoformat() if river_last else None,
                          flood_last_report_at=local_iso(fl.last_at, tz),
                          flood_reports_used=fl.used, flood_reports_excluded=fl.excluded),
    )


# ---------------------------------------------------------------------------
# Admin (X-API-Key)
# ---------------------------------------------------------------------------
def require_api_key(x_api_key: str | None = Header(None)) -> None:
    if not settings.api_key:
        raise HTTPException(status_code=503, detail="Endpoint admin dimatikan: API_KEY belum diisi di .env")
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Header X-API-Key salah atau tidak ada")


@app.post("/api/admin/refresh", status_code=202, tags=["Admin"], dependencies=[Depends(require_api_key)])
def refresh(background: BackgroundTasks, full: bool = False) -> dict:
    """Jalankan pipeline di latar belakang. Default: snapshot + prakiraan; `full=true`: semua job."""
    from pipeline.run import main as run_pipeline

    jobs = ["all"] if full else ["sync", "raw", "forecasts", "rivers", "views"]
    background.add_task(run_pipeline, jobs)
    return {"accepted": True, "jobs": jobs, "at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat()}


# Dasbor statis (harus dipasang terakhir supaya tidak menutupi /api).
app.mount("/", StaticFiles(directory=REPO_ROOT / "web", html=True), name="web")

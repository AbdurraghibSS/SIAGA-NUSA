-- Skema SIAGA NUSA · idempotent, aman dijalankan berulang (CREATE ... IF NOT EXISTS).
--
-- Lapisan data:
--   raw_payloads            ELT: envelope JSON apa adanya (jsonb), diolah belakangan di SQL
--   forecast_bmkg           ETL: prakiraan resmi BMKG per 3 jam, sudah dibersihkan di pandas
--   forecast_hourly         ETL: prakiraan Open-Meteo per jam, satu baris per (run, jam)
--   obs_daily               ETL: hujan harian ERA5 (reanalysis) untuk akumulasi & label Model A
--   flood_reports           ETL: laporan banjir PetaBencana Jabodetabek + penanda latihan/uji
--   quarantine              baris yang ditolak validasi, disimpan untuk diperiksa
--   ingest_runs             log setiap job pipeline (untuk halaman Status)

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS locations (
    slug  TEXT PRIMARY KEY,
    city  TEXT NOT NULL,
    name  TEXT NOT NULL,
    adm4  TEXT NOT NULL,
    lat   DOUBLE PRECISION NOT NULL,
    lon   DOUBLE PRECISION NOT NULL,
    tz    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_payloads (
    source      TEXT NOT NULL,
    location    TEXT NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL,
    status      INTEGER,
    error       TEXT,
    payload     JSONB,
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source, location, fetched_at)
);

CREATE TABLE IF NOT EXISTS forecast_bmkg (
    location          TEXT NOT NULL REFERENCES locations(slug),
    analysis_at       TIMESTAMPTZ NOT NULL,   -- waktu terbit prakiraan BMKG
    valid_at          TIMESTAMPTZ NOT NULL,   -- jam yang diprakirakan (awal blok 3 jam)
    first_fetched_at  TIMESTAMPTZ NOT NULL,   -- snapshot pertama yang memuat terbitan ini
    weather_code      INTEGER,
    weather_desc      TEXT,
    precip_mm         REAL,
    temperature_c     REAL,
    humidity_pct      REAL,
    cloud_cover_pct   REAL,
    wind_speed_kmh    REAL,
    wind_from         TEXT,
    PRIMARY KEY (location, analysis_at, valid_at)
);

CREATE TABLE IF NOT EXISTS forecast_hourly (
    location          TEXT NOT NULL REFERENCES locations(slug),
    issued_at         TIMESTAMPTZ NOT NULL,   -- = fetched_at snapshot (Open-Meteo tidak memberi waktu terbit)
    valid_at          TIMESTAMPTZ NOT NULL,
    precip_mm         REAL,
    rain_mm           REAL,
    precip_prob_pct   REAL,
    temperature_c     REAL,
    humidity_pct      REAL,
    pressure_hpa      REAL,
    wind_speed_kmh    REAL,
    wind_dir_deg      REAL,
    cloud_cover_pct   REAL,
    PRIMARY KEY (location, issued_at, valid_at)
);
CREATE INDEX IF NOT EXISTS idx_forecast_hourly_valid ON forecast_hourly (location, valid_at);

CREATE TABLE IF NOT EXISTS obs_daily (
    location   TEXT NOT NULL REFERENCES locations(slug),
    date       DATE NOT NULL,                 -- hari WIB/WITA lokal 00–24
    dataset    TEXT NOT NULL,                 -- era5 | era5_land
    precip_mm  REAL,
    PRIMARY KEY (location, date, dataset)
);

CREATE TABLE IF NOT EXISTS flood_reports (
    pkey              BIGINT PRIMARY KEY,
    created_at        TIMESTAMPTZ NOT NULL,
    lon               DOUBLE PRECISION NOT NULL,
    lat               DOUBLE PRECISION NOT NULL,
    region_code       TEXT,
    flood_depth_cm    INTEGER,
    text              TEXT,
    has_image         BOOLEAN NOT NULL,
    source            TEXT,
    cell              TEXT NOT NULL,          -- sel grid 0,05°
    exclusion_reason  TEXT,                   -- NULL = dipakai; selain itu latihan/uji/ledakan
    geom              GEOMETRY(Point, 4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)) STORED
);
CREATE INDEX IF NOT EXISTS idx_flood_reports_created ON flood_reports (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_flood_reports_geom ON flood_reports USING GIST (geom);

CREATE TABLE IF NOT EXISTS quarantine (
    id          BIGSERIAL PRIMARY KEY,
    job         TEXT NOT NULL,
    reason      TEXT NOT NULL,
    record      JSONB NOT NULL,
    record_hash TEXT GENERATED ALWAYS AS (md5(record::text)) STORED,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (job, record_hash)                 -- baris yang sama tidak dikarantina dua kali
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id             BIGSERIAL PRIMARY KEY,
    job            TEXT NOT NULL,
    started_at     TIMESTAMPTZ NOT NULL,
    finished_at    TIMESTAMPTZ,
    status         TEXT NOT NULL,             -- running | ok | failed
    rows_read      INTEGER NOT NULL DEFAULT 0,
    rows_loaded    INTEGER NOT NULL DEFAULT 0,
    rows_rejected  INTEGER NOT NULL DEFAULT 0,
    detail         TEXT
);
CREATE INDEX IF NOT EXISTS idx_ingest_runs_job ON ingest_runs (job, started_at DESC);

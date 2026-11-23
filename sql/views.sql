-- Transformasi SQL setelah load (pola ELT sesi 11) dan query analitik (sesi 8).
-- Dijalankan ulang setiap pipeline selesai; semua CREATE OR REPLACE.

-- Kategori intensitas hujan harian BMKG (sama dengan pipeline/rainfall.py).
CREATE OR REPLACE FUNCTION bmkg_category(mm DOUBLE PRECISION) RETURNS TEXT
LANGUAGE SQL IMMUTABLE AS $$
    SELECT CASE
        WHEN mm IS NULL THEN NULL
        WHEN mm < 0.5   THEN 'tidak hujan'
        WHEN mm < 20    THEN 'ringan'
        WHEN mm < 50    THEN 'sedang'
        WHEN mm < 100   THEN 'lebat'
        WHEN mm < 150   THEN 'sangat lebat'
        ELSE 'ekstrem'
    END
$$;

-- 1. Daftar run Open-Meteo per lokasi, run_rank 1 = terbaru (window function DENSE_RANK).
CREATE OR REPLACE VIEW v_hourly_runs AS
SELECT
    location,
    issued_at,
    COUNT(*) AS n_hours,
    DENSE_RANK() OVER (PARTITION BY location ORDER BY issued_at DESC) AS run_rank
FROM forecast_hourly
GROUP BY location, issued_at;

-- 2. Perubahan prakiraan: run terbaru vs run sebelumnya pada jam yang sama (CTE + JOIN).
CREATE OR REPLACE VIEW v_forecast_change AS
WITH runs AS (
    SELECT location, issued_at, run_rank FROM v_hourly_runs WHERE run_rank <= 2
),
latest AS (
    SELECT f.* FROM forecast_hourly f
    JOIN runs r ON r.location = f.location AND r.issued_at = f.issued_at AND r.run_rank = 1
),
previous AS (
    SELECT f.* FROM forecast_hourly f
    JOIN runs r ON r.location = f.location AND r.issued_at = f.issued_at AND r.run_rank = 2
)
SELECT
    l.location,
    l.valid_at,
    l.issued_at             AS latest_issued_at,
    p.issued_at             AS previous_issued_at,
    l.precip_mm             AS precip_latest,
    p.precip_mm             AS precip_previous,
    l.precip_mm - p.precip_mm AS precip_delta
FROM latest l
LEFT JOIN previous p ON p.location = l.location AND p.valid_at = l.valid_at;

-- 3. Terbitan BMKG terbaru per lokasi.
CREATE OR REPLACE VIEW v_bmkg_latest AS
SELECT b.*
FROM forecast_bmkg b
JOIN (
    SELECT location, MAX(analysis_at) AS analysis_at FROM forecast_bmkg GROUP BY location
) last USING (location, analysis_at);

-- 4. Hujan harian ERA5 + akumulasi bergulir 3 & 7 hari (window SUM ... RANGE) + kategori.
CREATE OR REPLACE VIEW v_obs_rolling AS
SELECT
    location,
    date,
    precip_mm,
    ROUND((SUM(precip_mm) OVER w3)::numeric, 1) AS precip_3d_mm,
    ROUND((SUM(precip_mm) OVER w7)::numeric, 1) AS precip_7d_mm,
    bmkg_category(precip_mm) AS category,
    precip_mm >= 20 AS is_moderate_plus        -- label Model A
FROM obs_daily
WHERE dataset = 'era5'
WINDOW
    w3 AS (PARTITION BY location ORDER BY date RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW),
    w7 AS (PARTITION BY location ORDER BY date RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW);

-- 5. Laporan banjir per hari: dipakai vs disaring (COUNT ... FILTER).
CREATE OR REPLACE VIEW v_flood_reports_daily AS
SELECT
    (created_at AT TIME ZONE 'Asia/Jakarta')::date AS date_wib,
    COUNT(*) FILTER (WHERE exclusion_reason IS NULL)     AS n_used,
    COUNT(*) FILTER (WHERE exclusion_reason IS NOT NULL) AS n_excluded
FROM flood_reports
GROUP BY 1;

-- 6. Kesegaran sumber: snapshot terakhir, lokasi yang berhasil di run terakhir,
--    dan jumlah gagal 24 jam terakhir. BMKG diambil per lokasi dengan jeda 1 detik,
--    jadi "run terakhir" = semua snapshot dalam 10 menit dari snapshot paling baru.
CREATE OR REPLACE VIEW v_source_freshness AS
WITH last AS (
    SELECT source, MAX(fetched_at) AS last_fetched_at FROM raw_payloads GROUP BY source
)
SELECT
    r.source,
    l.last_fetched_at,
    MAX(r.fetched_at) FILTER (WHERE r.error IS NULL)                                   AS last_ok_at,
    COUNT(DISTINCT r.location) FILTER (
        WHERE r.fetched_at > l.last_fetched_at - INTERVAL '10 minutes' AND r.error IS NULL) AS n_locations_ok_last,
    COUNT(DISTINCT r.location)                                                         AS n_locations,
    COUNT(*) FILTER (WHERE r.fetched_at > NOW() - INTERVAL '24 hours')                 AS n_24h,
    COUNT(*) FILTER (WHERE r.fetched_at > NOW() - INTERVAL '24 hours' AND r.error IS NOT NULL) AS n_failed_24h
FROM raw_payloads r
JOIN last l USING (source)
GROUP BY r.source, l.last_fetched_at;

-- 7. Estimasi hujan per jam untuk jam yang sudah lewat: ambil nilai dari run Open-Meteo
--    TERBARU yang memuat jam itu (DISTINCT ON). ERA5 tertinggal ±5 hari, jadi hujan
--    72 jam terakhir untuk indeks risiko diambil dari sini. Ini estimasi model, bukan pengukuran.
CREATE OR REPLACE VIEW v_rain_recent_est AS
SELECT DISTINCT ON (location, valid_at)
    location, valid_at, issued_at, precip_mm
FROM forecast_hourly
ORDER BY location, valid_at, issued_at DESC;

-- 8. Frekuensi banjir historis per kota (komponen indeks risiko): proporsi HARI musim
--    hujan (Nov–Apr, 2017/18–2024/25) yang punya ≥1 laporan warga dalam radius 5 km.
--    Ukuran "musim yang punya laporan" (plan awal) mentok di 8/8 untuk Jakarta (1.520
--    laporan) maupun Bogor (18 laporan), jadi tidak membedakan apa-apa; proporsi hari
--    membedakan (±25 persen vs ±1 persen). Bias: kepadatan laporan juga mencerminkan jumlah pengguna.
--    Hanya kota di dalam cakupan laporan (convex hull semua laporan) yang dihitung;
--    kota lain tidak muncul = komponen tidak tersedia, bukan nol.
DROP VIEW IF EXISTS v_flood_season_freq;
CREATE VIEW v_flood_season_freq AS
WITH hull AS (
    SELECT ST_ConvexHull(ST_Collect(geom)) AS g FROM flood_reports WHERE exclusion_reason IS NULL
),
covered AS (
    SELECT l.slug, ST_SetSRID(ST_MakePoint(l.lon, l.lat), 4326)::geography AS pt
    FROM locations l, hull
    WHERE ST_Contains(hull.g, ST_SetSRID(ST_MakePoint(l.lon, l.lat), 4326))
),
season_days AS (
    SELECT d::date AS date
    FROM generate_series(DATE '2017-11-01', DATE '2025-04-30', INTERVAL '1 day') d
    WHERE EXTRACT(MONTH FROM d) IN (11, 12, 1, 2, 3, 4)
),
flood_days AS (
    SELECT c.slug, (f.created_at AT TIME ZONE 'Asia/Jakarta')::date AS date, COUNT(*) AS n_reports
    FROM covered c
    JOIN flood_reports f
      ON f.exclusion_reason IS NULL AND ST_DWithin(f.geom::geography, c.pt, 5000)
    GROUP BY 1, 2
)
SELECT
    c.slug                                            AS location,
    COUNT(fd.date)                                    AS flood_days,
    (SELECT COUNT(*) FROM season_days)                AS season_days,
    COALESCE(SUM(fd.n_reports), 0)                    AS n_reports,
    ROUND(COUNT(fd.date)::numeric / (SELECT COUNT(*) FROM season_days), 4) AS freq
FROM covered c
LEFT JOIN flood_days fd ON fd.slug = c.slug AND fd.date IN (SELECT date FROM season_days)
GROUP BY c.slug;

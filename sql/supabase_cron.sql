-- Pemicu jadwal GitHub Actions dari Supabase (pg_cron + pg_net). KHUSUS Supabase, bukan DB lokal.
--
-- Kenapa: cron `schedule:` GitHub hanya best-effort. Nyatanya snapshot.yml (tiap jam) cuma jalan
-- 2–3×/hari, dan alerts.yml (tiap 15 menit) tidak jalan sama sekali berjam-jam, sehingga dasbor
-- Vercel tertinggal. pg_cron di Supabase tepat waktu; tiap tick memanggil API workflow_dispatch.
-- `schedule:` di workflow tetap ada sebagai cadangan (job idempoten, concurrency group mencegah
-- dua run bersamaan).
--
-- Token GitHub (fine-grained PAT, repo SIAGA-NUSA saja, izin Actions: read & write) disimpan di
-- Supabase Vault dengan nama 'github_dispatch_token'. File ini tidak memuat token; isi lewat
-- scripts/setup_supabase_cron.py. Aman dijalankan ulang: cron.schedule dengan nama sama = update.
-- Waktu pg_cron di Supabase = UTC.

CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

-- Skema privat: tidak diekspos Data API Supabase (hanya `public` yang diekspos).
CREATE SCHEMA IF NOT EXISTS ops;
REVOKE ALL ON SCHEMA ops FROM PUBLIC;

CREATE OR REPLACE FUNCTION ops.dispatch_workflow(workflow TEXT)
RETURNS BIGINT
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    token TEXT;
BEGIN
    SELECT decrypted_secret INTO token
    FROM vault.decrypted_secrets
    WHERE name = 'github_dispatch_token';
    IF token IS NULL THEN
        RAISE EXCEPTION 'secret Vault github_dispatch_token belum diisi';
    END IF;

    -- Asinkron: id request dikembalikan langsung, respons (204 = sukses) muncul di net._http_response.
    RETURN net.http_post(
        url := 'https://api.github.com/repos/AbdurraghibSS/SIAGA-NUSA/actions/workflows/'
               || workflow || '/dispatches',
        body := jsonb_build_object('ref', 'main'),
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || token,
            'Accept', 'application/vnd.github+json',
            'X-GitHub-Api-Version', '2022-11-28',
            'User-Agent', 'siaga-nusa-pg-cron',
            'Content-Type', 'application/json'
        ),
        timeout_milliseconds := 10000
    );
END;
$$;

REVOKE ALL ON FUNCTION ops.dispatch_workflow(TEXT) FROM PUBLIC, anon, authenticated;

-- Jadwal sama dengan `schedule:` di masing-masing workflow.
SELECT cron.schedule('gh-alerts',   '*/15 * * * *', $$SELECT ops.dispatch_workflow('alerts.yml')$$);
SELECT cron.schedule('gh-snapshot', '17 * * * *',   $$SELECT ops.dispatch_workflow('snapshot.yml')$$);
SELECT cron.schedule('gh-daily',    '30 22 * * *',  $$SELECT ops.dispatch_workflow('daily.yml')$$);

-- Riwayat run pg_cron (±120 baris/hari) dibuang setelah 7 hari supaya kuota 500 MB tidak termakan.
SELECT cron.schedule('purge-cron-history', '0 3 * * 0',
    $$DELETE FROM cron.job_run_details WHERE end_time < NOW() - INTERVAL '7 days'$$);

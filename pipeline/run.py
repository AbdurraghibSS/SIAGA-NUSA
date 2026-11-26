"""Pipeline SIAGA NUSA · extract → transform → load.

    python -m pipeline.run all              # semua job, berurutan
    python -m pipeline.run forecasts        # hanya prakiraan BMKG + Open-Meteo
    python -m pipeline.run sync forecasts views

Job:
  init       buat tabel + isi lokasi pilot
  sync       ambil snapshot terbaru dari branch data-snapshots
  snapshot   ambil snapshot BMKG + Open-Meteo langsung (dipakai scheduler; tanpa git)
  alerts     peringatan dini cuaca BMKG (nowcast CAP) → weather_alerts, tiap 15 menit di scheduler
  raw        ELT: muat envelope mentah ke raw_payloads (jsonb)
  forecasts  ETL: bersihkan BMKG & Open-Meteo di pandas lalu muat
  history    ETL: hujan harian ERA5 dari data/raw/open-meteo
  floods     ETL: laporan banjir PetaBencana dari data/raw/petabencana
  archive    ETL: prakiraan terbit sehari sebelumnya (Previous Runs, 4 model) untuk Model A
  predict    Model A: peluang hujan ≥20 mm besok per kota (model @champion dari MLflow)
  rivers     ETL: debit sungai GloFAS (riwayat per tahun + 14 hari terakhir + prakiraan 7 hari)
  views      transformasi SQL (view analitik)
  knowledge  RAG: PDF panduan BNPB/BMKG/BPBD di docs/ → Qdrant (tidak ikut `all`)
Semua job idempotent: menjalankan ulang tidak membuat baris ganda.
"""

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import text

from pipeline import db
from pipeline.config import settings
from pipeline.ingest import glofas, openmeteo, petabencana, previous_runs
from pipeline.ingest.http import make_session
from pipeline.locations import PILOT_LOCATIONS
from pipeline.rivers import RIVER_POINTS
from pipeline.sync import sync_snapshots
from pipeline.transform.floods import flood_frame
from pipeline.transform.previous_runs import files_frame as previous_runs_frame
from pipeline.transform.rivers import glofas_files_frame, glofas_items_frame
from pipeline.transform.forecast import (bmkg_frame, era5_frame, era5_items_frame, openmeteo_frame,
                                         raw_payload_frame, read_envelopes)

log = logging.getLogger("pipeline")
SINCE: date | None = None  # diisi --since-days; None = baca seluruh arsip snapshot

ERA5_FILES = {
    "era5": "archive_daily_era5_2017_2026.json",
    "era5_land": "archive_daily_era5_land_2017_2026.json",
}


def job_sync() -> None:
    with db.JobRun("sync") as run:
        run.read = sync_snapshots(settings.snapshot_dir, settings.snapshot_remote, settings.snapshot_branch)
        run.loaded = run.read


def job_snapshot() -> None:
    """Ambil snapshot BMKG + Open-Meteo LANGSUNG ke data/snapshots (kode yang sama dengan GitHub Actions).

    Dipakai scheduler di server/container, yang tidak punya akses git ke branch data-snapshots.
    Branch tetap berguna sebagai arsip saat server mati; keduanya bisa dimuat bersama karena
    kunci raw_payloads (sumber, lokasi, waktu ambil) unik."""
    from pipeline.ingest import snapshot

    with db.JobRun("snapshot_local") as run:
        before = sum(1 for _ in settings.snapshot_dir.rglob("*.json")) if settings.snapshot_dir.exists() else 0
        code = snapshot.main(["--out", str(settings.snapshot_dir)])
        after = sum(1 for _ in settings.snapshot_dir.rglob("*.json"))
        run.read = run.loaded = after - before
        if code != 0:
            raise RuntimeError("semua panggilan BMKG dan Open-Meteo gagal")


def job_alerts() -> None:
    """Peringatan dini cuaca BMKG: RSS daftar aktif → CAP yang belum ada di DB → weather_alerts (PostGIS)."""
    from pipeline.ingest import bmkg_alerts as ba

    with db.JobRun("alerts_bmkg") as run:
        session = make_session()
        resp = session.get(ba.RSS_URL, timeout=30)
        resp.raise_for_status()
        items = ba.parse_rss(resp.text)
        run.read = len(items)
        with db.engine.connect() as conn:
            known = set(conn.execute(text("SELECT identifier FROM weather_alerts")).scalars())
        rows, bad = [], []
        for it in items:
            if it["guid"] in known:
                continue
            try:
                cap = session.get(it["link"], timeout=30)
                cap.raise_for_status()
                rows.append(ba.parse_cap(cap.text, it["link"]))
            except Exception as exc:  # satu CAP rusak tidak menggagalkan yang lain
                bad.append({**it, "reason": f"{type(exc).__name__}: {str(exc)[:200]}"})
        if rows:
            with db.engine.begin() as conn:
                run.loaded = sum(conn.execute(text("""
                    INSERT INTO weather_alerts (identifier, msg_type, sent_at, effective_at, expires_at, event, urgency,
                        severity, certainty, headline, description, area_desc, province, places, infographic_url, cap_url, geom)
                    VALUES (:identifier, :msg_type, :sent_at, :effective_at, :expires_at, :event, :urgency, :severity,
                        :certainty, :headline, :description, :area_desc, :province, :places, :infographic_url, :cap_url,
                        CASE WHEN CAST(:geom_wkt AS text) IS NULL THEN NULL ELSE
                          ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_GeomFromText(CAST(:geom_wkt AS text), 4326)), 3)) END)
                    ON CONFLICT (identifier) DO NOTHING
                """), r).rowcount for r in rows)
        run.rejected = len(bad)
        if bad:
            db.quarantine("alerts_bmkg", pd.DataFrame(bad))
        run.detail = f"{len(items)} aktif di RSS, {len(rows)} CAP baru"


def job_raw() -> None:
    for source in ("bmkg", "open-meteo"):
        with db.JobRun(f"raw_{source}") as run:
            envelopes = read_envelopes(settings.snapshot_dir, source, since=SINCE)
            run.read = len(envelopes)
            run.loaded = db.load_dataframe(raw_payload_frame(envelopes), "raw_payloads",
                                           ("source", "location", "fetched_at"), casts={"payload": "jsonb"})


def job_forecasts() -> None:
    with db.JobRun("forecast_bmkg") as run:
        envelopes = read_envelopes(settings.snapshot_dir, "bmkg", since=SINCE)
        clean, rejects = bmkg_frame(envelopes)
        run.read = len(envelopes)
        run.loaded = db.load_dataframe(clean, "forecast_bmkg", ("location", "analysis_at", "valid_at"))
        run.rejected = len(rejects)
        db.quarantine("forecast_bmkg", rejects)
        run.detail = f"{len(clean)} baris unik dari {len(envelopes)} snapshot"

    with db.JobRun("forecast_openmeteo") as run:
        envelopes = read_envelopes(settings.snapshot_dir, "open-meteo", since=SINCE)
        clean, rejects = openmeteo_frame(envelopes)
        run.read = len(envelopes)
        run.loaded = db.load_dataframe(clean, "forecast_hourly", ("location", "issued_at", "valid_at"))
        run.rejected = len(rejects)
        db.quarantine("forecast_openmeteo", rejects)
        run.detail = f"{clean['issued_at'].nunique() if not clean.empty else 0} run"


def _today_wib() -> date:
    return datetime.now(ZoneInfo("Asia/Jakarta")).date()


def job_history() -> None:
    """ERA5 harian: backfill dari file arsip, lalu susul hari yang belum ada lewat API."""
    with db.JobRun("history_era5") as run:
        session = make_session()
        filled = []
        for dataset, filename in ERA5_FILES.items():
            path = settings.raw_dir / "open-meteo" / filename
            if path.exists():
                df = era5_frame(path, PILOT_LOCATIONS, dataset)
                run.read += len(df)
                run.loaded += db.load_dataframe(df, "obs_daily", ("location", "date", "dataset"))
            with db.engine.connect() as conn:
                # Tanggal terakhir yang dimiliki SEMUA lokasi, supaya lokasi yang tertinggal ikut tersusul.
                last = conn.execute(text(
                    "SELECT MIN(d) FROM (SELECT MAX(date) AS d FROM obs_daily WHERE dataset = :ds GROUP BY location) t"
                ), {"ds": dataset}).scalar()
            start = (last + timedelta(days=1)) if last else date(2017, 1, 1)
            end = _today_wib() - timedelta(days=1)
            if start > end:
                continue
            items = openmeteo.fetch_daily_archive(session, PILOT_LOCATIONS, f"{start}", f"{end}", model=dataset)
            df = era5_items_frame(items, PILOT_LOCATIONS, dataset)
            run.read += len(df)
            run.loaded += db.load_dataframe(df, "obs_daily", ("location", "date", "dataset"))
            filled.append(f"{dataset} s.d. {df['date'].max() if not df.empty else last}")
        run.detail = "; ".join(filled) or None


def job_floods() -> None:
    """Tarik ulang arsip PetaBencana bulan lalu + bulan ini, lalu muat semua arsip.

    Penanda ledakan bisa berubah setelah laporan baru masuk di sel-jam yang sama,
    jadi `exclusion_reason` laporan lama ikut diperbarui.
    """
    with db.JobRun("floods_petabencana") as run:
        archive_dir = settings.raw_dir / "petabencana"
        today = _today_wib()
        prev_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        if petabencana.main(["--start", f"{prev_month:%Y-%m}", "--end", f"{today:%Y-%m}",
                             "--out", str(archive_dir), "--refresh"]) != 0:
            log.warning("floods: sebagian bulan gagal ditarik, memakai arsip lokal yang ada")
        floods, rejects, n_raw = flood_frame(archive_dir)
        run.read = n_raw
        run.loaded = db.load_dataframe(floods, "flood_reports", ("pkey",), update=("exclusion_reason",))
        run.rejected = len(rejects)
        db.quarantine("floods_petabencana", rejects)
        n_excluded = int(floods["exclusion_reason"].notna().sum())
        run.detail = f"{len(floods)} laporan banjir Jabodetabek, {n_excluded} ditandai latihan/uji/ledakan"


def job_archive() -> None:
    """Prakiraan yang terbit sehari sebelumnya (fitur Model A tanpa contekan).

    Tahun berjalan ditarik ulang setiap eksekusi (sampai prakiraan besok), jadi baris
    yang sudah ada diperbarui.
    """
    with db.JobRun("forecast_archive") as run:
        session = make_session()
        archive_dir = settings.raw_dir / "open-meteo"
        previous_runs.backfill(session, PILOT_LOCATIONS, archive_dir, _today_wib() + timedelta(days=1))
        df = previous_runs_frame(list(archive_dir.glob("previous_runs_*.json")), PILOT_LOCATIONS)
        run.read = len(df)
        value_cols = [c for c in df.columns if c not in ("location", "date", "model")]
        run.loaded = db.load_dataframe(df, "forecast_archive_daily", ("location", "date", "model"), update=tuple(value_cols))
        run.detail = (f"{df['model'].nunique()} model, {df['date'].min()} s.d. {df['date'].max()}"
                      if not df.empty else "kosong")


def job_predict() -> None:
    """Hitung ulang peluang hujan ≥20 mm untuk besok. Butuh paket grup `ml` dan server MLflow."""
    from pipeline.predict import predict

    with db.JobRun("predict_model_a") as run:
        df = predict(make_session(), db.engine, _today_wib())
        run.read = len(df)
        run.loaded = db.load_dataframe(df, "rain_predictions", ("location", "target_date", "model_name", "model_version"),
                                       update=("issued_at", "prob", "level"))
        top = df.sort_values("prob", ascending=False).iloc[0]
        run.detail = (f"{df['model_name'].iloc[0]} v{df['model_version'].iloc[0]} untuk {df['target_date'].iloc[0]}; "
                      f"tertinggi {top['location']} {top['prob']:.0%} ({top['level']})")


def job_rivers() -> None:
    """Debit GloFAS: riwayat per tahun dari file (ditarik sekali), lalu hari terakhir + prakiraan.

    Nilai beberapa hari terakhir dan prakiraan berubah tiap hari, jadi baris yang sudah
    ada diperbarui (`update`), bukan dilewati.
    """
    with db.JobRun("rivers_glofas") as run:
        session = make_session()
        today = datetime.now(ZoneInfo("UTC")).date()
        history_dir = settings.raw_dir / "glofas"
        glofas.backfill(session, RIVER_POINTS, history_dir, today)
        history, rejects = glofas_files_frame(list(history_dir.glob("daily_*.json")), RIVER_POINTS, today)
        recent, bad = glofas_items_frame(glofas.fetch_recent(session, RIVER_POINTS), RIVER_POINTS, today)
        # Angka terbaru menang untuk tanggal yang sama.
        df = pd.concat([history, recent]).drop_duplicates(["point", "date"], keep="last")
        run.read = len(history) + len(recent)
        run.loaded = db.load_dataframe(df, "river_daily", ("point", "date"), update=("discharge_m3s", "is_forecast"))
        rejects = pd.concat([rejects, bad])
        run.rejected = len(rejects)
        db.quarantine("rivers_glofas", rejects)
        run.detail = f"{len(RIVER_POINTS)} titik, {df['date'].min()} s.d. {df['date'].max()} (prakiraan sejak {today})"


def job_knowledge() -> None:
    """RAG: PDF panduan di docs/ → embedding Gemini → Qdrant. Tidak ikut `all` (butuh PDF lokal + kunci Gemini)."""
    from pipeline import knowledge

    with db.JobRun("knowledge_rag") as run:
        s = knowledge.build(settings.knowledge_dir)
        run.read = run.loaded = s["chunks"]
        run.detail = f"{settings.qdrant_collection}: " + ", ".join(s["docs"])
        if s["missing"]:
            run.detail += f"; PDF belum ada: {', '.join(s['missing'])}"


def job_views() -> None:
    with db.JobRun("views") as run:
        db.run_sql_file("views.sql")
        run.detail = "sql/views.sql"


JOBS = {
    "init": db.init_db,
    "sync": job_sync,
    "snapshot": job_snapshot,
    "alerts": job_alerts,
    "raw": job_raw,
    "forecasts": job_forecasts,
    "history": job_history,
    "floods": job_floods,
    "archive": job_archive,
    "predict": job_predict,
    "rivers": job_rivers,
    "views": job_views,
    "knowledge": job_knowledge,
}
ALL = ["init", "sync", "alerts", "raw", "forecasts", "history", "floods", "archive", "rivers", "views", "predict"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline SIAGA NUSA")
    parser.add_argument("jobs", nargs="+", choices=[*JOBS, "all"], help="job yang dijalankan, berurutan")
    parser.add_argument("--since-days", type=int, default=None,
                        help="raw/forecasts hanya membaca snapshot N hari terakhir (scheduler: 2)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s")

    global SINCE
    SINCE = (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=args.since_days)) if args.since_days else None
    jobs = ALL if "all" in args.jobs else args.jobs
    if "init" not in jobs:
        db.init_db()  # tabel ingest_runs harus ada sebelum job lain mencatat dirinya
    failed = []
    for name in jobs:
        try:
            JOBS[name]()
        except Exception:  # satu job gagal tidak menghentikan yang lain; status tercatat di ingest_runs
            log.exception("job %s gagal", name)
            failed.append(name)
    if failed:
        log.error("gagal: %s", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

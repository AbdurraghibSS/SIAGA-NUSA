"""Penjadwal pipeline (plan §8: APScheduler) · menjaga dasbor dan agen tetap memakai data hari ini.

    python -m pipeline.scheduler          # jalan terus; di Docker: service `scheduler`

Dua kelompok job, keduanya memanggil `pipeline.run.main` (job yang sama dengan CLI, tercatat
di ingest_runs sehingga terlihat di halaman Status):

  15 menit                 alerts (peringatan dini cuaca BMKG, nowcast CAP)
  per jam  (menit ke-5)    snapshot → raw → forecasts → views
                           Prakiraan BMKG + Open-Meteo diambil langsung, tanpa git.
  harian   (05.30 WIB)     history → floods → rivers → archive → views → predict
                           ERA5 tertinggal ±5 hari dan GloFAS/Previous Runs berubah harian,
                           jadi cukup sekali. `predict` butuh server MLflow (Model A @champion).

Saat mulai: job per jam langsung dijalankan sekali, dan job harian ikut dijalankan kalau
prediksi Model A untuk besok belum ada (mis. laptop baru dinyalakan siang hari).
Satu job tidak pernah berjalan dobel (max_instances=1); jadwal yang terlewat saat mesin
tidur dijalankan sekali saja begitu bangun (coalesce + misfire_grace_time).
"""

import logging
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from pipeline import db, run

log = logging.getLogger("scheduler")
TZ = ZoneInfo("Asia/Jakarta")

HOURLY = ["snapshot", "raw", "forecasts", "views"]
DAILY = ["history", "floods", "rivers", "archive", "views", "predict"]


def hourly() -> int:
    # Hanya snapshot 2 hari terakhir yang dibaca: cukup untuk menutup jeda, tetap cepat walau arsip tumbuh.
    return run.main([*HOURLY, "--since-days", "2"])


def alerts() -> int:
    return run.main(["alerts"])


def daily() -> int:
    return run.main(DAILY)


def prediction_ready_for_tomorrow() -> bool:
    tomorrow = (datetime.now(TZ) + timedelta(days=1)).date()
    try:
        with db.engine.connect() as conn:
            latest = conn.execute(text("SELECT MAX(target_date) FROM rain_predictions")).scalar()
    except Exception:  # tabel belum ada: anggap belum siap
        return False
    return latest is not None and latest >= tomorrow


def build_scheduler():
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched = BlockingScheduler(timezone=TZ, job_defaults={
        "coalesce": True, "max_instances": 1, "misfire_grace_time": 30 * 60})
    sched.add_job(hourly, CronTrigger(minute=5, timezone=TZ), id="hourly", name="prakiraan per jam")
    sched.add_job(daily, CronTrigger(hour=5, minute=30, timezone=TZ), id="daily", name="data harian + Model A")
    # Nowcast BMKG berlaku 1–3 jam, jadi diperiksa tiap 15 menit (RSS kecil; CAP hanya yang baru).
    sched.add_job(alerts, CronTrigger(minute="*/15", timezone=TZ), id="alerts", name="peringatan dini BMKG")
    return sched


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s")
    db.init_db()
    sched = build_scheduler()
    log.info("mulai: menjalankan job per jam + peringatan dini sekali")
    hourly()
    alerts()
    if not prediction_ready_for_tomorrow():
        log.info("prediksi besok belum ada: menjalankan job harian sekarang")
        daily()
    for job in sched.get_jobs():
        log.info("terjadwal: %-24s berikutnya %s", job.name, job.trigger.get_next_fire_time(None, datetime.now(TZ)))
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

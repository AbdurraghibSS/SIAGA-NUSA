"""Jadwal scheduler tanpa menjalankan job."""

from datetime import datetime

from pipeline import scheduler


def test_jobs_and_next_fire_times():
    sched = scheduler.build_scheduler()
    jobs = {j.id: j for j in sched.get_jobs()}
    assert set(jobs) == {"hourly", "daily", "alerts"}
    now = datetime(2026, 11, 26, 14, 40, tzinfo=scheduler.TZ)
    assert jobs["hourly"].trigger.get_next_fire_time(None, now) == datetime(2026, 11, 26, 15, 5, tzinfo=scheduler.TZ)
    assert jobs["daily"].trigger.get_next_fire_time(None, now) == datetime(2026, 11, 27, 5, 30, tzinfo=scheduler.TZ)
    assert jobs["alerts"].trigger.get_next_fire_time(None, now) == datetime(2026, 11, 26, 14, 45, tzinfo=scheduler.TZ)


def test_hourly_reads_only_recent_snapshots(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler.run, "main", lambda argv: calls.append(argv) or 0)
    scheduler.hourly()
    assert calls == [["snapshot", "raw", "forecasts", "views", "--since-days", "2"]]
    assert scheduler.DAILY[-1] == "predict"  # prediksi dihitung setelah data harian segar

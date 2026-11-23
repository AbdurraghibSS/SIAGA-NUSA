"""Akses database · SQLAlchemy engine, skema, dan load idempotent.

Pola sesi 9 & 11: `create_engine` dari settings, DDL `IF NOT EXISTS`, dan insert
`ON CONFLICT DO NOTHING` supaya pipeline aman dijalankan berulang kali.
Load memakai tabel staging sementara: DataFrame → `_stg_<tabel>` (pandas `to_sql`)
→ `INSERT ... SELECT ... ON CONFLICT DO NOTHING`. Satu round-trip, dan jumlah baris
baru akurat dari `rowcount`.
"""

import json
import logging
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import create_engine, text

from pipeline.config import REPO_ROOT, settings
from pipeline.locations import PILOT_LOCATIONS

log = logging.getLogger(__name__)

engine = create_engine(settings.database_url, pool_pre_ping=True)
SQL_DIR = REPO_ROOT / "sql"


def run_sql_file(name: str) -> None:
    """Jalankan file .sql di folder `sql/` dalam satu transaksi."""
    sql = (SQL_DIR / name).read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)
    log.info("SQL %s selesai", name)


def init_db() -> None:
    """Buat tabel (kalau belum ada) dan isi tabel referensi lokasi."""
    run_sql_file("schema.sql")
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO locations (slug, city, name, adm4, lat, lon, tz)
                VALUES (:slug, :city, :name, :adm4, :lat, :lon, :tz)
                ON CONFLICT (slug) DO UPDATE
                SET city = EXCLUDED.city, name = EXCLUDED.name, adm4 = EXCLUDED.adm4,
                    lat = EXCLUDED.lat, lon = EXCLUDED.lon, tz = EXCLUDED.tz
            """),
            [
                {"slug": l.slug, "city": l.city, "name": l.name, "adm4": l.adm4, "lat": l.lat, "lon": l.lon, "tz": l.tz}
                for l in PILOT_LOCATIONS
            ],
        )


def load_dataframe(df: pd.DataFrame, table: str, key: tuple[str, ...], casts: dict[str, str] | None = None,
                   update: tuple[str, ...] = ()) -> int:
    """Insert baris baru; duplikat kunci dilewati, atau diperbarui kalau kolomnya ada di `update`
    dan nilainya berubah. Kembalikan jumlah baris yang masuk atau berubah."""
    if df.empty:
        return 0
    casts = casts or {}
    staging = f"_stg_{table}"
    cols = list(df.columns)
    col_list = ", ".join(f'"{c}"' for c in cols)
    select_list = ", ".join(f'"{c}"::{casts[c]}' if c in casts else f'"{c}"' for c in cols)
    key_list = ", ".join(f'"{c}"' for c in key)
    if update:
        sets = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update)
        changed = " OR ".join(f'{table}."{c}" IS DISTINCT FROM EXCLUDED."{c}"' for c in update)
        on_conflict = f"DO UPDATE SET {sets} WHERE {changed}"
    else:
        on_conflict = "DO NOTHING"
    with engine.begin() as conn:
        df.to_sql(staging, conn, if_exists="replace", index=False, chunksize=5000, method="multi")
        result = conn.execute(text(
            f"INSERT INTO {table} ({col_list}) SELECT {select_list} FROM {staging} "
            f"ON CONFLICT ({key_list}) {on_conflict}"
        ))
        conn.execute(text(f"DROP TABLE {staging}"))
    return result.rowcount


def quarantine(job: str, rejects: pd.DataFrame) -> int:
    """Simpan baris yang ditolak validasi (kolom `reason` wajib) ke `quarantine`. Kembalikan jumlah baru."""
    if rejects.empty:
        return 0
    rows = [
        {"job": job, "reason": r.pop("reason"), "record": json.dumps(r, default=str, ensure_ascii=False)}
        for r in rejects.to_dict(orient="records")
    ]
    new = 0
    with engine.begin() as conn:
        for row in rows:
            new += conn.execute(text(
                "INSERT INTO quarantine (job, reason, record) VALUES (:job, :reason, CAST(:record AS jsonb)) "
                "ON CONFLICT (job, record_hash) DO NOTHING"
            ), row).rowcount
    return new


class JobRun:
    """Catat satu eksekusi job di `ingest_runs` (untuk halaman Status).

        with JobRun("forecast_bmkg") as run:
            run.read += len(raw)
            run.loaded += load_dataframe(...)
    """

    def __init__(self, job: str):
        self.job = job
        self.read = 0
        self.loaded = 0
        self.rejected = 0
        self.detail: str | None = None
        self._id: int | None = None

    def __enter__(self) -> "JobRun":
        with engine.begin() as conn:
            self._id = conn.execute(
                text("INSERT INTO ingest_runs (job, started_at, status) VALUES (:job, :t, 'running') RETURNING id"),
                {"job": self.job, "t": datetime.now(timezone.utc)},
            ).scalar_one()
        log.info("[%s] mulai", self.job)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        status = "ok" if exc is None else "failed"
        detail = self.detail if exc is None else f"{type(exc).__name__}: {exc}"[:500]
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE ingest_runs
                    SET finished_at = :t, status = :status, rows_read = :read,
                        rows_loaded = :loaded, rows_rejected = :rejected, detail = :detail
                    WHERE id = :id
                """),
                {"t": datetime.now(timezone.utc), "status": status, "read": self.read, "loaded": self.loaded,
                 "rejected": self.rejected, "detail": detail, "id": self._id},
            )
        log.info("[%s] %s · dibaca %d · masuk %d · ditolak %d%s", self.job, status, self.read, self.loaded,
                 self.rejected, f" · {detail}" if detail else "")
        return False  # jangan telan exception

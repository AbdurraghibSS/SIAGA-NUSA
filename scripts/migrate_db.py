"""Salin database SIAGA NUSA dari Postgres lokal (Docker) ke Postgres cloud (Supabase).

    python scripts/migrate_db.py                       # target = SUPABASE_SESSION_URL di .env
    python scripts/migrate_db.py --target-env NAMA_VAR

Langkah (aman dijalankan ulang):
1. Skema dibuat di target dengan file yang sama (sql/schema.sql, lalu sql/views.sql).
2. Tabel aplikasi di target dikosongkan (TRUNCATE ... CASCADE).
3. Data disalin per tabel dengan COPY (format teks), urut sesuai foreign key. Kolom GENERATED
   (geom laporan banjir, hash karantina) dihitung ulang oleh target, jadi tidak ikut disalin.
4. Sequence id diset ulang ke MAX(id), lalu jumlah baris sumber dan target dibandingkan.

URL koneksi tidak pernah dicetak. Pakai session pooler (port 5432): transaction pooler tidak
cocok untuk DDL dan COPY yang panjang.
"""

import argparse
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values

REPO = Path(__file__).resolve().parent.parent
# Urutan menghormati foreign key: locations dulu, river_points sebelum river_daily.
TABLES = [
    "locations", "river_points",
    "raw_payloads", "forecast_bmkg", "forecast_hourly", "obs_daily", "forecast_archive_daily",
    "rain_predictions", "river_daily", "flood_reports", "weather_alerts",
    "quarantine", "ingest_runs", "agent_logs",
]


def plain(url: str) -> str:
    """URL SQLAlchemy ('postgresql+psycopg://') → URL libpq."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def copy_columns(conn, table: str) -> list[str]:
    rows = conn.execute("""
        SELECT a.attname FROM pg_attribute a
        WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped AND a.attgenerated = ''
        ORDER BY a.attnum
    """, (table,)).fetchall()
    return [r[0] for r in rows]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target-env", default="SUPABASE_SESSION_URL", help="nama variabel di .env berisi URL target")
    args = ap.parse_args(argv)

    env = dotenv_values(REPO / ".env")
    from pipeline.config import settings  # sumber = DATABASE_URL lokal (default docker)

    source, target = plain(settings.database_url), env.get(args.target_env)
    if not target:
        print(f"{args.target_env} kosong di .env", file=sys.stderr)
        return 1

    with psycopg.connect(source) as src, psycopg.connect(plain(target), prepare_threshold=None) as dst:
        print("1/4 skema di target")
        for name in ("schema.sql", "views.sql"):
            dst.execute((REPO / "sql" / name).read_text(encoding="utf-8"))
        dst.commit()

        print("2/4 kosongkan tabel target")
        dst.execute("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE")
        dst.commit()

        print("3/4 salin data")
        for table in TABLES:
            cols = ", ".join(f'"{c}"' for c in copy_columns(src, table))
            with src.cursor().copy(f"COPY {table} ({cols}) TO STDOUT") as out, \
                    dst.cursor().copy(f"COPY {table} ({cols}) FROM STDIN") as inp:
                for chunk in out:
                    inp.write(chunk)
            dst.commit()
            print(f"   {table}")

        print("4/4 sequence + cek jumlah baris")
        for table in TABLES:
            if "id" not in copy_columns(dst, table):
                continue
            seq = dst.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,)).fetchone()[0]
            if seq:
                dst.execute(f"SELECT setval(%s, COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)", (seq,))
        dst.commit()
        bad = 0
        for table in TABLES:
            n_src = src.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            n_dst = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            ok = n_src == n_dst
            bad += not ok
            print(f"   {'✓' if ok else '✗'} {table:24s} {n_src:>8} → {n_dst:>8}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

"""Pasang pemicu jadwal GitHub Actions di Supabase (pg_cron + pg_net), lihat sql/supabase_cron.sql.

    python scripts/setup_supabase_cron.py            # simpan token ke Vault + pasang jadwal
    python scripts/setup_supabase_cron.py --test     # ... lalu picu alerts.yml sekali sebagai uji
    python scripts/setup_supabase_cron.py --check    # hanya tampilkan jadwal, run terakhir, respons GitHub

Butuh di .env: SUPABASE_SESSION_URL dan GITHUB_DISPATCH_TOKEN (fine-grained PAT, repo SIAGA-NUSA
saja, izin Actions: read & write). Token maupun URL koneksi tidak pernah dicetak. Aman dijalankan
ulang; mengganti token yang kedaluwarsa cukup dengan mengubah .env lalu menjalankan ulang skrip ini.
"""

import argparse
import sys
import time
from pathlib import Path

import psycopg
from dotenv import dotenv_values

REPO = Path(__file__).resolve().parent.parent
SECRET = "github_dispatch_token"


def plain(url: str) -> str:
    """URL SQLAlchemy ('postgresql+psycopg://') → URL libpq."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def upsert_token(conn, token: str) -> None:
    row = conn.execute("SELECT id FROM vault.secrets WHERE name = %s", (SECRET,)).fetchone()
    if row:
        conn.execute("SELECT vault.update_secret(%s, %s)", (row[0], token))
    else:
        conn.execute("SELECT vault.create_secret(%s, %s, %s)",
                     (token, SECRET, "PAT GitHub untuk workflow_dispatch SIAGA-NUSA"))


def show(conn) -> None:
    print("Jadwal pg_cron:")
    for name, sched, active in conn.execute(
            "SELECT jobname, schedule, active FROM cron.job ORDER BY jobname"):
        print(f"   {name:20s} {sched:14s} {'aktif' if active else 'NONAKTIF'}")

    print("Run terakhir per jadwal (UTC):")
    for name, start, status, msg in conn.execute("""
        SELECT DISTINCT ON (j.jobname) j.jobname, d.start_time, d.status, d.return_message
        FROM cron.job_run_details d JOIN cron.job j USING (jobid)
        ORDER BY j.jobname, d.start_time DESC
    """):
        print(f"   {name:20s} {start:%Y-%m-%d %H:%M} {status:10s} {(msg or '')[:80]}")

    # pg_net menyimpan respons ±6 jam. 204 = GitHub menerima dispatch; 401/403 = token salah/kurang izin.
    print("Respons GitHub terakhir (pg_net):")
    for created, code, err in conn.execute("""
        SELECT created, status_code, error_msg FROM net._http_response ORDER BY created DESC LIMIT 8
    """):
        print(f"   {created:%Y-%m-%d %H:%M} {code}  {err or ''}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="hanya tampilkan status, tanpa mengubah apa pun")
    ap.add_argument("--test", action="store_true", help="setelah setup, picu alerts.yml sekali")
    args = ap.parse_args(argv)

    env = dotenv_values(REPO / ".env")
    url, token = env.get("SUPABASE_SESSION_URL"), env.get("GITHUB_DISPATCH_TOKEN")
    if not url:
        print("SUPABASE_SESSION_URL kosong di .env", file=sys.stderr)
        return 1

    with psycopg.connect(plain(url), prepare_threshold=None) as conn:
        if not args.check:
            if not token:
                print("GITHUB_DISPATCH_TOKEN kosong di .env", file=sys.stderr)
                return 1
            upsert_token(conn, token)
            conn.execute((REPO / "sql" / "supabase_cron.sql").read_text(encoding="utf-8"))
            conn.commit()
            print("Token tersimpan di Vault, jadwal terpasang.")

        if args.test:
            conn.execute("SELECT ops.dispatch_workflow('alerts.yml')")
            conn.commit()
            time.sleep(5)  # pg_net mengirim setelah commit, lewat background worker

        show(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())

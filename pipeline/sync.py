"""Ambil snapshot prakiraan dari branch `data-snapshots` ke `data/snapshots/`.

GitHub Actions menarik BMKG + Open-Meteo setiap 3 jam dan meng-commit hasilnya ke
branch terpisah (lihat `.github/workflows/snapshot.yml`). Di sini branch itu di-fetch,
lalu folder `snapshots/` diekstrak dengan `git archive`. File snapshot tidak pernah
ditimpa di branch, jadi ekstrak ulang selalu aman.
"""

import io
import logging
import subprocess
import tarfile
from pathlib import Path

from pipeline.config import REPO_ROOT

log = logging.getLogger(__name__)


def sync_snapshots(dest_dir: Path, remote: str = "origin", branch: str = "data-snapshots") -> int:
    """Fetch branch snapshot lalu ekstrak ke `dest_dir` (= .../snapshots). Kembalikan jumlah file."""
    subprocess.run(["git", "fetch", "--quiet", remote, branch], cwd=REPO_ROOT, check=True)
    tar_bytes = subprocess.run(
        ["git", "archive", "--format=tar", f"{remote}/{branch}", "snapshots"],
        cwd=REPO_ROOT, check=True, capture_output=True,
    ).stdout
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
        members = [m for m in tar.getmembers() if m.isfile()]
        tar.extractall(dest_dir.parent, members=members, filter="data")
    log.info("sync: %d file snapshot dari %s/%s", len(members), remote, branch)
    return len(members)

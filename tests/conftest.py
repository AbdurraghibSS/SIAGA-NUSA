"""Tes tidak membaca .env pribadi (kunci, password, URL cloud): semua pengaturan memakai default."""

import os

os.environ.setdefault("SIAGA_ENV_FILE", os.devnull)

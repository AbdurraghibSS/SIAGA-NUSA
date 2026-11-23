# SIAGA NUSA backend · FastAPI (hanya /api, /health, /docs; dasbor disajikan container frontend).
#   docker compose up -d --build backend
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Kode dipasang editable supaya REPO_ROOT tetap /app (dipakai untuk sql/ dan web/).
COPY pyproject.toml ./
COPY pipeline ./pipeline
COPY api ./api
COPY sql ./sql
RUN pip install -e .

# Jalankan sebagai pengguna biasa, bukan root.
RUN useradd --create-home --uid 1000 siaga && mkdir -p /app/data && chown -R siaga /app/data
USER siaga

ENV SERVE_WEB=false
EXPOSE 8011
CMD ["uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8011"]

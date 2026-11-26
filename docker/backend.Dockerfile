# SIAGA NUSA backend · FastAPI (hanya /api, /health, /docs; dasbor disajikan container frontend).
# Image yang sama dipakai service `scheduler` (EXTRAS=[ml], command python -m pipeline.scheduler).
#   docker compose up -d --build backend
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Kode dipasang editable supaya REPO_ROOT tetap /app (dipakai untuk sql/ dan web/).
# EXTRAS: grup dependensi tambahan, mis. "[ml]" untuk image scheduler (Model A butuh scikit-learn + MLflow).
ARG EXTRAS=""
# 1) Dependensi saja, dibaca dari pyproject.toml. Layer ini hanya dibangun ulang kalau pyproject berubah,
#    jadi mengubah kode tidak memasang ulang paket ML (±10 menit → beberapa detik).
COPY pyproject.toml ./
RUN python -c "import tomllib; p = tomllib.load(open('pyproject.toml', 'rb'))['project']; \
extras = [e for e in '${EXTRAS}'.strip('[]').split(',') if e]; \
print('\n'.join(p['dependencies'] + [d for e in extras for d in p['optional-dependencies'][e]]))" > /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt
# 2) Kode, dipasang tanpa dependensi.
COPY pipeline ./pipeline
COPY api ./api
COPY sql ./sql
RUN pip install --no-deps -e .

# Jalankan sebagai pengguna biasa, bukan root.
RUN useradd --create-home --uid 1000 siaga && mkdir -p /app/data && chown -R siaga /app/data
USER siaga

ENV SERVE_WEB=false
EXPOSE 8011
CMD ["uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8011"]

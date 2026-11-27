# SIAGA NUSA frontend · nginx menyajikan web/ dan meneruskan /api ke backend.
#   docker compose up -d --build frontend
FROM nginx:1.27-alpine

# Template diisi envsubst saat container mulai (WEB_PORT, API_UPSTREAM).
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
# Basic auth opsional (BASIC_AUTH_USER / BASIC_AUTH_PASSWORD), dibuat saat container mulai.
COPY --chmod=755 docker/frontend-auth.sh /docker-entrypoint.d/15-basic-auth.sh
COPY web /usr/share/nginx/html

ENV WEB_PORT=8010 \
    API_UPSTREAM=127.0.0.1:8011

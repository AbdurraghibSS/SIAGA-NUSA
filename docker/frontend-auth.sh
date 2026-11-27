#!/bin/sh
# Basic auth opsional untuk akses dari luar (tunnel). Dijalankan entrypoint nginx sebelum envsubst.
# BASIC_AUTH_PASSWORD kosong → auth mati (pemakaian lokal). Terisi → semua halaman dan /api butuh login.
set -eu
AUTH_CONF=/etc/nginx/auth.conf
if [ -n "${BASIC_AUTH_PASSWORD:-}" ]; then
  # Skema {PLAIN} didukung nginx; file hanya ada di dalam container dan hanya terbaca root/nginx.
  printf '%s:{PLAIN}%s\n' "${BASIC_AUTH_USER:-tim}" "$BASIC_AUTH_PASSWORD" > /etc/nginx/htpasswd
  chown root:nginx /etc/nginx/htpasswd && chmod 640 /etc/nginx/htpasswd
  printf 'auth_basic "SIAGA NUSA";\nauth_basic_user_file /etc/nginx/htpasswd;\n' > "$AUTH_CONF"
  echo "frontend-auth: basic auth AKTIF untuk pengguna '${BASIC_AUTH_USER:-tim}'"
else
  echo 'auth_basic off;' > "$AUTH_CONF"
  echo "frontend-auth: basic auth mati (BASIC_AUTH_PASSWORD kosong)"
fi

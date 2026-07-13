#!/usr/bin/env bash
# bb-weapons production deploy. Runs ON the VPS (weapons.bloodngold.com).
#   ssh root@46.225.141.38 "bash /var/www/bb-weapons/deploy.sh"
# Pulls the repo, reinstalls deps, restarts gunicorn on 8005, verifies 200.
set -euo pipefail

APP=/var/www/bb-weapons
VENV=$APP/venv
PORT=8005

echo "[1/4] pull"
git -C "$APP" pull --ff-only

echo "[2/4] deps"
"$VENV/bin/pip" install -q -r "$APP/webapp/requirements.txt"

echo "[3/4] restart gunicorn on $PORT"
fuser -k ${PORT}/tcp 2>/dev/null || true
sleep 1
"$VENV/bin/gunicorn" --chdir "$APP/webapp" --workers 2 \
  --bind 127.0.0.1:${PORT} "app:create_app()" --daemon \
  --error-logfile /var/log/gunicorn-weapons-error.log

echo "[4/4] verify"
sleep 2
code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:${PORT}/)
echo "  / -> $code"
[ "$code" = "200" ] || { echo "DEPLOY FAILED: / not 200"; exit 1; }
echo "OK: bb-weapons live on 127.0.0.1:${PORT} (nginx -> weapons.bloodngold.com)"

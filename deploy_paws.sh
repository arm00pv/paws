#!/bin/bash
# deploy_paws.sh — publish PAWS to the watchtower (public surface).
# The watchtower network cycles (relay through NYC) — retries built in.
# Routes to add to the Caddyfile when this runs:
#   /paws/*        -> the Flutter web build (this script pushes it to
#                     /var/www/paws_web and caddy serves it as static)
#   /paws-api/*    -> reverse_proxy 127.0.0.1:8235 (the FastAPI)
set -e
# SECURITY NOTE (auditor): the hardcoded password is a DEV artifact.
# For a real launch: use an SSH key + the secrets.env file, never a
# password in the repo. This script is the dev path only.
WT="zixen@100.94.237.87"
PASS="roy1130"

echo "[1] SCP the paws backend + web build (retry loop)..."
for i in 1 2 3 4 5; do
  if sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
      -r /home/zixen15/paws "$WT":/home/zixen/ 2>/dev/null; then
    echo "    pushed (attempt $i)"; break
  fi
  echo "    attempt $i failed — retry in 20s"; sleep 20
done

echo "[2] install deps + start the API on the watchtower"
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$WT" << 'EOF'
  pip3 install -q fastapi uvicorn python-barcode pillow treepoem 2>/dev/null || true
  pgrep -f paws_api.py >/dev/null || nohup python3 /home/zixen/paws/backend/paws_api.py \
      > /tmp/paws_api.log 2>&1 &
  echo "  paws api starting on 127.0.0.1:8235"
EOF

echo "[3] serve the web build (static)"
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$WT" \
  "mkdir -p /var/www/paws_web && cp -r /home/zixen/paws/app/build/web/* /var/www/paws_web/ 2>/dev/null || true"

echo "[4] Caddyfile must gain (IN-PLACE write — bind-mount gotcha):"
echo "    handle_path /paws/* { root * /var/www/paws_web; file_server }"
echo "    handle /paws-api/* { reverse_proxy 127.0.0.1:8235 }"
echo "    then: docker exec caddy caddy reload --config /etc/caddy/Caddyfile"
echo "DONE — verify https://marquezhv.com/paws/ once the network settles"

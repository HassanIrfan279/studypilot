#!/usr/bin/env bash
# Build + (re)start StudyPilot. Also use this after every `git pull`.
set -euo pipefail
cd "$(dirname "$0")"
for f in ../backend/.env ../backend/credentials.json; do
  [ -f "$f" ] || { echo "Missing $f - upload it first (see DEPLOY.md)"; exit 1; }
done
IP=$(curl -s -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip)
export DOMAIN=${DOMAIN:-${IP//./-}.sslip.io}
sudo DOMAIN="$DOMAIN" docker compose up -d --build
echo
echo "Waiting for StudyPilot to start..."
for i in $(seq 1 40); do
  if curl -fsS "https://$DOMAIN/health" >/dev/null 2>&1; then
    echo "LIVE:  https://$DOMAIN"; exit 0
  fi
  sleep 5
done
echo "Not answering yet. Check:  sudo docker compose logs --tail=80"

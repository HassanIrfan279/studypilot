#!/usr/bin/env bash
# Build + (re)start StudyPilot. Also use this after every `git pull`.
# Works on any Linux server (Google Cloud, Azure, ...).
# Domain: DOMAIN=... the first time (it is remembered in deploy/.domain), else <ip-with-dashes>.sslip.io
set -euo pipefail
cd "$(dirname "$0")"
for f in ../backend/.env ../backend/credentials.json; do
  [ -f "$f" ] || { echo "Missing $f - upload it first (see the deploy guide)"; exit 1; }
done

public_ip() {
  curl -s -m 2 -H "Metadata-Flavor: Google" \
    http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip \
  || curl -s -m 5 https://api.ipify.org
}

if [ -n "${DOMAIN:-}" ]; then
  echo "$DOMAIN" > .domain                      # remember it for next time
elif [ -f .domain ]; then
  DOMAIN=$(cat .domain)
else
  IP=$(public_ip)
  DOMAIN="${IP//./-}.sslip.io"
fi
export DOMAIN
echo "Starting StudyPilot at https://$DOMAIN"
sudo DOMAIN="$DOMAIN" docker compose up -d --build
echo
echo "Waiting for StudyPilot to start..."
for i in $(seq 1 40); do
  if curl -fsS "https://$DOMAIN/health" >/dev/null 2>&1; then
    echo "LIVE:  https://$DOMAIN"; exit 0
  fi
  sleep 5
done
echo "Not answering yet. Wait a minute and run this again, or check:  sudo docker compose logs --tail=80"

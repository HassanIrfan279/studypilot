#!/usr/bin/env bash
# One-time setup on a fresh Debian/Ubuntu server (Google Cloud, Azure, ...). Safe to run again.
set -euo pipefail

# 1) 2 GB swap: small servers (1-2 GB RAM) need it to build the app
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# 2) Docker + git
sudo apt-get update -qq && sudo apt-get install -y -qq git curl >/dev/null
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo systemctl enable --now docker

# 3) Code
if [ ! -d ~/studypilot ]; then
  git clone https://github.com/HassanIrfan279/studypilot.git ~/studypilot
fi

IP=$(curl -s -m 2 -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip \
  || curl -s -m 5 https://api.ipify.org)
echo
echo "Setup done. Server IP: $IP  (free sslip.io domain: ${IP//./-}.sslip.io)"
echo "Next: upload .env and credentials.json, then run deploy/start.sh"

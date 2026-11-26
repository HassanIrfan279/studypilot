#!/usr/bin/env bash
# One-time setup on a fresh Debian/Ubuntu Google Cloud VM. Safe to run again.
set -euo pipefail

# 1) 2 GB swap: the free e2-micro has 1 GB RAM, not enough to build the app without it
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# 2) Docker + git
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo apt-get update -qq && sudo apt-get install -y -qq git curl >/dev/null
sudo systemctl enable --now docker

# 3) Code
if [ ! -d ~/studypilot ]; then
  git clone https://github.com/HassanIrfan279/studypilot.git ~/studypilot
fi

IP=$(curl -s -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip)
echo
echo "Setup done. Your free domain is:  ${IP//./-}.sslip.io"
echo "Next: upload .env and credentials.json, then run deploy/start.sh"

#!/usr/bin/env bash
# Optional: move your laptop's StudyPilot data (sign-in, prep packs, notes, CV, internships) to the server.
# First upload studypilot.db (and cv.pdf if you have one) with the SSH window's "Upload file" button.
set -euo pipefail
cd "$(dirname "$0")"
[ -f ~/studypilot.db ] || { echo "Upload studypilot.db first (from D:\claude\agentathon\studypilot\backend\)"; exit 1; }
sudo docker compose stop app
sudo docker compose cp ~/studypilot.db app:/data/studypilot.db && echo "copied studypilot.db"
[ -f ~/cv.pdf ] && sudo docker compose cp ~/cv.pdf app:/data/cv.pdf && echo "copied cv.pdf"
sudo docker compose start app
rm -f ~/studypilot.db ~/cv.pdf
echo "Done. Open your site: everything from your laptop is there."

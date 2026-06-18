#!/bin/bash
#
# deploy-pi.sh — run on the PRODUCTION Raspberry Pi.
# One command, ONE service: pull latest code -> build the Svelte UI (static SPA)
# -> copy it into app-ui/static/ui/ -> update + restart the FastAPI backend, which
# serves BOTH the API (/api) and the UI (/) on port 8000. No node server, no proxy.
#
# First-time setup on the Pi:
#   git clone https://github.com/SystemsCyber/SSS2-GUI.git
#   cd SSS2-GUI && git switch New-Gui-CAN
#   python3 -m venv app-ui/venv
#   sudo cp scripts/systemd/sss2-backend.service /etc/systemd/system/   # edit User=/paths first
#   sudo systemctl daemon-reload && sudo systemctl enable sss2-backend.service
#   ./scripts/deploy-pi.sh
#
set -euo pipefail

# ===== Config (override via env if your names/paths differ) =====
REMOTE="${REMOTE:-origin}"                       # remote that points at the GitHub repo
BRANCH="${BRANCH:-New-Gui-CAN}"
BACKEND_SERVICE="${BACKEND_SERVICE:-sss2-backend.service}"

# The UI talks to the backend on the SAME origin (FastAPI serves both), so the
# relative default is correct. No reason to change this in the single-service setup.
export VITE_API_BASE="${VITE_API_BASE:-/api}"

echo "--------------------------------------"
echo "SSS2-GUI deployment (Raspberry Pi, single service)"
echo "--------------------------------------"

# Move to repo root (this script lives in scripts/)
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
echo "Repo : $ROOT"

# 1) Pull latest code
echo "==> Pulling latest from $REMOTE/$BRANCH..."
git pull "$REMOTE" "$BRANCH"

# 2) Build the UI (static SPA -> ui/build) and copy into the backend's static dir
echo "==> Building UI..."
cd "$ROOT/ui"
npm ci || npm install
npm run build                      # adapter-static -> ui/build (index.html + _app/...)
cd "$ROOT"
echo "==> Publishing UI to app-ui/static/ui/..."
mkdir -p app-ui/static/ui
rm -rf app-ui/static/ui/*
cp -r ui/build/* app-ui/static/ui/

# 3) Backend (FastAPI / app-ui) — update Python deps
echo "==> Updating backend dependencies..."
if [ ! -d app-ui/venv ]; then
  echo "    Creating venv at app-ui/venv..."
  python3 -m venv app-ui/venv
fi
# shellcheck disable=SC1091
source app-ui/venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r app-ui/requirements.txt
deactivate

# 4) Restart the single backend service (serves API + UI)
echo "==> Restarting $BACKEND_SERVICE..."
sudo systemctl restart "$BACKEND_SERVICE"

echo "--------------------------------------"
echo "Deployment complete."
echo "  backend ($BACKEND_SERVICE): $(systemctl is-active "$BACKEND_SERVICE" || true)"
echo "  Open:  http://<pi-ip>:8000/"
echo "--------------------------------------"

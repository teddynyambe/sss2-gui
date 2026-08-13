#!/bin/bash
#
# update-prod.sh — ONE command to update the production appliance from GitHub.
# Run on the Pi:   ./scripts/update-prod.sh
#
# Force-syncs the repo to the remote (robust against rewritten/diverged history),
# rebuilds the UI, updates Python deps, clears the kiosk browser cache, and
# restarts BOTH the backend and the kiosk so new UI shows immediately.
#
# Override defaults via env, e.g.:  REMOTE=origin BRANCH=main ./scripts/update-prod.sh
#
set -euo pipefail

REMOTE="${REMOTE:-teddy}"
BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
BACKEND_SERVICE="${BACKEND_SERVICE:-sss2-backend.service}"
KIOSK_SERVICE="${KIOSK_SERVICE:-sss2-kiosk.service}"
KIOSK_USER="${KIOSK_USER:-$USER}"

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
echo "=================================================="
echo " SSS2 production update"
echo "   repo   : $ROOT"
echo "   source : $REMOTE/$BRANCH"
echo "=================================================="

# 1) Force-sync to the remote (discards local drift; untracked files like the
#    built static/ui and the proprietary .xlsx are left alone).
echo "==> Syncing to $REMOTE/$BRANCH..."
git fetch "$REMOTE" --prune
git reset --hard "$REMOTE/$BRANCH"

# 2) Build the UI and publish it into the backend's static dir.
echo "==> Building UI..."
( cd ui && { npm ci || npm install; } && npm run build )
echo "==> Publishing UI to app-ui/static/ui/..."
mkdir -p app-ui/static/ui
rm -rf app-ui/static/ui/*
cp -r ui/build/* app-ui/static/ui/

# 3) Backend Python deps.
echo "==> Updating backend deps..."
[ -d app-ui/venv ] || python3 -m venv app-ui/venv
app-ui/venv/bin/pip install --upgrade pip >/dev/null
app-ui/venv/bin/pip install -r app-ui/requirements.txt

# 4) Clear the kiosk browser cache so the new build always loads.
KIOSK_HOME="$(getent passwd "$KIOSK_USER" | cut -d: -f6)"
if [ -n "${KIOSK_HOME:-}" ] && [ -d "$KIOSK_HOME/.config/sss2-kiosk" ]; then
  echo "==> Clearing kiosk browser cache ($KIOSK_HOME/.config/sss2-kiosk)..."
  sudo rm -rf "$KIOSK_HOME/.config/sss2-kiosk"
fi

# 5) Restart backend + kiosk.
echo "==> Restarting services..."
sudo systemctl restart "$BACKEND_SERVICE"
sudo systemctl restart "$KIOSK_SERVICE"

echo "=================================================="
echo " Update complete."
echo "   backend : $(systemctl is-active "$BACKEND_SERVICE" || true)"
echo "   kiosk   : $(systemctl is-active "$KIOSK_SERVICE" || true)"
echo "=================================================="

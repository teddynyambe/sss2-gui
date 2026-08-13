#!/bin/bash
# On-device "Update & Restart GUI", triggered from the Admin panel.
# Spawned DETACHED by the backend (routers/system.py) as the app user, so it
# survives the service restart it performs at the end. Progress -> a log file.
#
# Student-level steps (git pull + UI build) run unprivileged; the final service
# restart goes through the root-owned helper via sudo.
set -u

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LOG=/tmp/sss2-kiosk-update.log

{
  echo "=== update started $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="
  cd "$REPO" || exit 1
  echo "--> git pull (current branch)"
  git pull --ff-only || { echo "git pull failed"; exit 1; }
  echo "--> build UI"
  ( cd ui && { npm ci || npm install; } && npm run build ) || { echo "UI build failed"; exit 1; }
  echo "--> publish to static/ui"
  mkdir -p app-ui/static/ui && rm -rf app-ui/static/ui/* && cp -r ui/build/* app-ui/static/ui/
  echo "--> restart services (via root helper)"
  sudo -n /usr/local/sbin/sss2-kiosk-admin restart-app
  echo "=== update finished $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="
} >>"$LOG" 2>&1

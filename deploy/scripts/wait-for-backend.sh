#!/bin/bash
# Block until the FastAPI backend answers, so the kiosk never opens before the
# app is serveable. Used as ExecStartPre of sss2-kiosk.service.
set -u
URL="${HEALTH_URL:-http://localhost:8000/api/health}"
TIMEOUT="${WAIT_TIMEOUT:-120}"      # seconds; 0 = wait forever

echo "wait-for-backend: polling $URL (timeout ${TIMEOUT}s)"
start=$SECONDS
while true; do
  if curl -fsS --max-time 2 "$URL" >/dev/null 2>&1; then
    echo "wait-for-backend: backend is up"
    exit 0
  fi
  if [ "$TIMEOUT" -gt 0 ] && [ $((SECONDS - start)) -ge "$TIMEOUT" ]; then
    # Don't fail the kiosk — the launcher page shows a friendly "disconnected"
    # screen and keeps retrying, so launch anyway.
    echo "wait-for-backend: timed out, launching kiosk with the launcher fallback"
    exit 0
  fi
  sleep 2
done

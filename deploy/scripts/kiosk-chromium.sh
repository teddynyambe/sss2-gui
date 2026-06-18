#!/bin/bash
# Launched INSIDE the cage Wayland compositor (see sss2-kiosk.service).
# Runs Chromium full-screen, no chrome, pointed at the launcher page.
set -u

# The launcher (file://) gates on backend health, then hands off to the app.
LAUNCHER="${KIOSK_LAUNCHER:-/var/www/sss2-gui-v2/deploy/kiosk/launcher.html}"
URL="file://${LAUNCHER}"

# Dedicated profile so we can scrub crash flags (prevents the "restore pages"
# bar after an unclean shutdown/power loss).
PROFILE="${HOME}/.config/sss2-kiosk"
mkdir -p "$PROFILE/Default"
PREFS="$PROFILE/Default/Preferences"
if [ -f "$PREFS" ]; then
  sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"[^"]*"/"exit_type":"Normal"/' "$PREFS" || true
fi

# Chromium binary differs by image (Raspberry Pi OS = chromium-browser).
BIN="$(command -v chromium-browser || command -v chromium)"

exec "$BIN" \
  --kiosk "$URL" \
  --user-data-dir="$PROFILE" \
  --ozone-platform=wayland \
  --start-fullscreen \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  --no-first-run \
  --fast --fast-start \
  --check-for-update-interval=31536000 \
  --autoplay-policy=no-user-gesture-required

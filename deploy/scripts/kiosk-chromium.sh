#!/bin/bash
# Launched INSIDE the cage Wayland compositor (see sss2-kiosk.service).
# Runs Chromium full-screen, no chrome, pointed at the launcher page.
set -u

# Per-host overrides (rotation, launcher path, etc.) — optional.
[ -r /etc/default/sss2-kiosk ] && . /etc/default/sss2-kiosk

# The launcher (file://) gates on backend health, then hands off to the app.
LAUNCHER="${KIOSK_LAUNCHER:-/var/www/sss2-gui-v2/deploy/kiosk/launcher.html}"
URL="file://${LAUNCHER}"

# --- Display + touch rotation --------------------------------------------------
# Runs inside the cage Wayland session, so wlr-randr can talk to it. wlroots maps
# touch input onto the rotated output automatically, keeping taps aligned.
#   KIOSK_ROTATE = normal | 90 | 180 | 270   (set in /etc/default/sss2-kiosk;
#   if the picture is rotated the WRONG way, swap 90 <-> 270)
ROTATE="${KIOSK_ROTATE:-90}"
if [ "$ROTATE" != "normal" ] && command -v wlr-randr >/dev/null 2>&1; then
  OUT="$(wlr-randr 2>/dev/null | awk 'NR==1{print $1; exit}')"
  [ -n "$OUT" ] && wlr-randr --output "$OUT" --transform "$ROTATE" || true
fi

# Start from a CLEAN profile every launch. A kiosk must never serve a stale app
# shell from browser cache, and nothing in this profile is worth keeping (HTTP
# cache + crash flags only). This makes "old UI after an update" impossible.
PROFILE="${HOME}/.config/sss2-kiosk"
rm -rf "$PROFILE"
mkdir -p "$PROFILE/Default"

# Chromium binary differs by image (Raspberry Pi OS = chromium-browser).
BIN="$(command -v chromium-browser || command -v chromium)"

exec "$BIN" \
  --kiosk "$URL" \
  --user-data-dir="$PROFILE" \
  --disk-cache-size=1 \
  --aggressive-cache-discard \
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

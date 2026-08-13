#!/bin/bash
#
# setup-appliance.sh — ONE-TIME provisioning for the Raspberry Pi kiosk appliance.
# Run with sudo on the Pi:   sudo ./scripts/setup-appliance.sh
#
# Installs dependencies, the CAN bring-up + kiosk systemd units, the sudoers rule
# for UI CAN control, sets the Pi to boot straight into the full-screen kiosk, and
# enables the backend. Paths/user are auto-substituted from where the repo lives.
#
# It does NOT edit /boot/firmware/config.txt (MCP2515 overlays) — that's hardware-
# specific and shown as a manual step at the end. Re-runnable (idempotent).
#
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo:  sudo ./scripts/setup-appliance.sh" >&2
  exit 1
fi

# Repo root (this script lives in scripts/) and the unprivileged app user.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="${APP_USER:-student}"
APP_UID="$(id -u "$APP_USER")"
SYSTEMD=/etc/systemd/system

echo "=============================================="
echo " SSS2 appliance setup"
echo "   repo : $ROOT"
echo "   user : $APP_USER (uid $APP_UID)"
echo "=============================================="

# 1) Packages -------------------------------------------------------------------
echo "==> Installing packages (cage, chromium, can-utils, curl, node, python venv)..."
apt-get update -y
apt-get install -y --no-install-recommends \
  cage wlr-randr chromium-browser can-utils curl \
  python3-venv nodejs npm || \
apt-get install -y --no-install-recommends \
  cage wlr-randr chromium can-utils curl python3-venv nodejs npm

# 2) Seat/GPU/input group access for the kiosk user -----------------------------
echo "==> Adding $APP_USER to video, render, input, tty, seat groups..."
for grp in video render input tty seat; do
  getent group "$grp" >/dev/null 2>&1 && usermod -aG "$grp" "$APP_USER" || true
done

# 3) Make repo scripts executable ----------------------------------------------
chmod +x "$ROOT"/scripts/*.sh "$ROOT"/deploy/scripts/*.sh

# 4) sudoers for UI-driven CAN up/down + kiosk admin ---------------------------
echo "==> Installing sudoers rules (CAN control + admin helper)..."
install -m 0440 "$ROOT/deploy/sudoers/sss2-can"    /etc/sudoers.d/sss2-can
install -m 0440 "$ROOT/deploy/sudoers/sss2-system" /etc/sudoers.d/sss2-system
# Adjust the username in the rules if not 'student'
sed -i "s/^student /$APP_USER /" /etc/sudoers.d/sss2-can /etc/sudoers.d/sss2-system
visudo -cf /etc/sudoers.d/sss2-can
visudo -cf /etc/sudoers.d/sss2-system

# 4b) Root-owned privileged admin helper (NOT the repo copy — repo is user-writable)
echo "==> Installing root-owned kiosk admin helper..."
install -m 0755 -o root -g root "$ROOT/deploy/scripts/sss2-kiosk-admin" /usr/local/sbin/sss2-kiosk-admin

# 4b-2) 'kiosk' shortcut + console login banner (how to get back to the kiosk)
echo "==> Installing 'kiosk' shortcut + console hint..."
install -m 0755 -o root -g root "$ROOT/deploy/scripts/kiosk"           /usr/local/bin/kiosk
install -m 0644             "$ROOT/deploy/profile.d/sss2-kiosk-hint.sh" /etc/profile.d/sss2-kiosk-hint.sh

# 4b-3) Desktop launcher: app menu + an icon on the user's Desktop
echo "==> Installing 'Return to Kiosk' desktop launcher..."
install -m 0644 "$ROOT/deploy/desktop/return-to-kiosk.desktop" /usr/share/applications/return-to-kiosk.desktop
DESKTOP_DIR="/home/$APP_USER/Desktop"
mkdir -p "$DESKTOP_DIR"
install -m 0755 -o "$APP_USER" -g "$APP_USER" \
  "$ROOT/deploy/desktop/return-to-kiosk.desktop" "$DESKTOP_DIR/return-to-kiosk.desktop"
# Mark trusted so file managers launch it without the "untrusted" prompt (best-effort)
sudo -u "$APP_USER" gio set "$DESKTOP_DIR/return-to-kiosk.desktop" metadata::trusted true 2>/dev/null || true

# 4c) Host config file: admin PIN + display rotation. Created once; never overwritten.
if [ ! -f /etc/default/sss2-kiosk ]; then
  echo "==> Writing /etc/default/sss2-kiosk (CHANGE THE PIN!)..."
  cat > /etc/default/sss2-kiosk <<'DEFAULTS'
# SSS2 kiosk host configuration.
# Display rotation for the touchscreen: normal | 90 | 180 | 270
KIOSK_ROTATE=90
# Admin-panel PIN. CHANGE THIS. Empty = admin panel disabled.
SYSTEM_ADMIN_PIN=246813
DEFAULTS
  chmod 0640 /etc/default/sss2-kiosk
fi

# 4d) Management access: SSH + a spare login console on Ctrl+Alt+F2
echo "==> Enabling SSH and a console VT (Ctrl+Alt+F2)..."
systemctl enable --now ssh 2>/dev/null || systemctl enable --now sshd 2>/dev/null || true
systemctl enable getty@tty2.service 2>/dev/null || true

# 5) Install systemd units, substituting ROOT/USER/UID --------------------------
install_unit() {  # <src> <dest> — rewrite repo path + user for this host, either convention
  sed -e "s#/var/www/sss2-gui-v2#$ROOT#g" \
      -e "s#/home/pi/sss2-gui-v2#$ROOT#g" \
      -e "s/^User=student\$/User=$APP_USER/" \
      -e "s/^User=pi\$/User=$APP_USER/" \
      -e "s#/home/student#/home/$APP_USER#g" \
      -e "s#/run/user/%U#/run/user/$APP_UID#g" \
      "$1" > "$2"
}
echo "==> Installing systemd units..."
install_unit "$ROOT/scripts/systemd/sss2-backend.service" "$SYSTEMD/sss2-backend.service"
cp           "$ROOT/deploy/systemd/can@.service"          "$SYSTEMD/can@.service"
install_unit "$ROOT/deploy/systemd/sss2-kiosk.service"    "$SYSTEMD/sss2-kiosk.service"

# 6) Backend venv (if missing) --------------------------------------------------
if [ ! -d "$ROOT/app-ui/venv" ]; then
  echo "==> Creating backend venv..."
  sudo -u "$APP_USER" python3 -m venv "$ROOT/app-ui/venv"
fi

# 7) Boot straight to the kiosk (no desktop, no login prompt on tty1) -----------
echo "==> Setting boot target to console + kiosk..."
systemctl set-default multi-user.target
for dm in lightdm gdm3 gdm; do systemctl disable "$dm" 2>/dev/null || true; done

# 8) Enable everything ----------------------------------------------------------
echo "==> Enabling services..."
systemctl daemon-reload
systemctl enable can@can0.service can@can1.service
systemctl enable sss2-backend.service
systemctl enable sss2-kiosk.service

echo
echo "=============================================="
echo " Setup complete. Remaining manual step:"
echo "=============================================="
cat <<EOF

1) Enable the dual MCP2515 CAN overlays. Edit /boot/firmware/config.txt and add
   (adjust oscillator + interrupt pins to YOUR HAT's wiring):

     dtparam=spi=on
     dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25
     dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=24

2) Build the UI + start the backend once (so /api/health responds):

     REMOTE=teddy ./scripts/deploy-pi.sh

3) Reboot:   sudo reboot

After reboot the Pi should: bring up can0/can1, start the backend, and open the
kiosk full-screen. Logs:  journalctl -u sss2-kiosk -u sss2-backend -u can@can0 -f
EOF

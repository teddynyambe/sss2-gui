# SSS2 Kiosk Appliance (Raspberry Pi 5, Bookworm)

Turns the Pi into a dedicated, no-login CAN-dashboard appliance: on power-up it
brings up `can0`/`can1`, starts the backend (FastAPI, which also serves the UI),
waits for it to be ready, then launches Chromium full-screen in kiosk mode with
auto-recovery. The UI can also start/stop the CAN interfaces on demand.

> **Architecture note:** this is a *single* service. FastAPI (`sss2-backend`) serves
> both the API (`/api`) and the built Svelte UI (`/`) on port **8000**. There is no
> separate "frontend" service and no Flask — the kiosk just waits on the backend.

## What gets installed

| Piece | File | Role |
|-------|------|------|
| CAN bring-up (templated) | [deploy/systemd/can@.service](../deploy/systemd/can@.service) | `can@can0`/`can@can1` — boot **and** UI start/stop |
| Backend | [scripts/systemd/sss2-backend.service](../scripts/systemd/sss2-backend.service) | uvicorn on :8000 (API + UI) |
| Kiosk | [deploy/systemd/sss2-kiosk.service](../deploy/systemd/sss2-kiosk.service) | `cage` + Chromium, full-screen |
| Health gate | [deploy/scripts/wait-for-backend.sh](../deploy/scripts/wait-for-backend.sh) | kiosk waits for `/api/health` |
| Chromium launch | [deploy/scripts/kiosk-chromium.sh](../deploy/scripts/kiosk-chromium.sh) | kiosk Chromium flags |
| Launcher page | [deploy/kiosk/launcher.html](../deploy/kiosk/launcher.html) | "Backend Disconnected" + auto-redirect |
| CAN sudo rule | [deploy/sudoers/sss2-can](../deploy/sudoers/sss2-can) | UI may `systemctl start/stop can@*` |
| Provisioner | [scripts/setup-appliance.sh](../scripts/setup-appliance.sh) | installs all of the above |
| App updates | [scripts/deploy-pi.sh](../scripts/deploy-pi.sh) | pull → build UI → restart backend |

## Install (run on the Pi)

```bash
cd /var/www/sss2-gui-v2
git fetch teddy && git checkout -B sss2_can_enabled teddy/sss2_can_enabled

# 1) Provision everything (packages, units, sudoers, boot-to-kiosk)
sudo ./scripts/setup-appliance.sh

# 2) Enable the dual MCP2515 overlays — edit to match YOUR HAT's wiring
sudo nano /boot/firmware/config.txt
#   dtparam=spi=on
#   dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25
#   dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=24

# 3) Build the UI + start the backend once
REMOTE=teddy ./scripts/deploy-pi.sh

# 4) Reboot into the appliance
sudo reboot
```

After reboot the screen should go: black → (splash, if configured) → **launcher**
("Connecting to backend…") → the dashboard, full-screen, no chrome.

## CAN interfaces

- **Boot:** `can@can0` and `can@can1` are enabled, so they come up automatically at
  250000 bit/s. Override per interface: create `/etc/default/can@can0` with
  `BITRATE=500000` and `sudo systemctl restart can@can0`.
- **From the UI:** the **Network** tab has a *CAN Interfaces* panel with Start/Stop
  per interface. Buttons call `POST /api/canctl/{can0|can1}/{up|down}`, which runs
  `sudo systemctl start|stop can@<iface>` (allowed by the sudoers rule).
- **Manually:**
  ```bash
  sudo systemctl start can@can0      # up
  sudo systemctl stop  can@can0      # down
  ip -details link show can0         # state + bitrate
  ```

## Auto-recovery & "Backend Disconnected"

- **Health gate:** `sss2-kiosk` won't open the browser until `/api/health` answers.
- **Launcher page** (`file://…/launcher.html`) is what Chromium actually opens. It
  polls the backend and only then redirects to the app — so during a cold start or
  backend restart the user sees a styled "Backend Disconnected — retrying" screen,
  never Chromium's raw error. It's a local file, so it loads even when the backend
  is down.
- **Crash recovery:** `Restart=always` on the kiosk service relaunches Chromium (and
  re-gates) if it ever exits. The SPA also auto-reconnects its WebSocket/poll.

## Splash screen (hide boot text)

```bash
sudo apt install -y plymouth plymouth-themes
# quiet boot + splash:
sudo sed -i 's/$/ quiet splash plymouth.ignore-serial-consoles/' /boot/firmware/cmdline.txt   # one line, append
sudo plymouth-set-default-theme -R spinner     # or a custom theme dir under /usr/share/plymouth/themes
```

## Hide the desktop entirely

`setup-appliance.sh` already does this: `systemctl set-default multi-user.target`
(boot to console, no desktop) and disables any display manager (lightdm/gdm). The
kiosk service owns `tty1` (`Conflicts=getty@tty1`), so there's no login prompt.

## Logging (journalctl)

```bash
journalctl -u sss2-backend -f          # API + UI server
journalctl -u sss2-kiosk   -f          # cage/Chromium
journalctl -u can@can0 -u can@can1     # interface bring-up
journalctl -b -u sss2-kiosk            # this boot only
```
All services log to the journal (no log files to rotate). Add persistent storage
with `sudo mkdir -p /var/log/journal && sudo systemctl restart systemd-journald`.

## Testing checklist

```bash
systemctl is-active sss2-backend sss2-kiosk can@can0 can@can1
curl -s http://localhost:8000/api/health            # JSON
curl -s http://localhost:8000/api/canctl/status     # interface states
ip -details link show can0                           # UP + bitrate
```
- Pull the touchscreen's USB / replug — kiosk should keep running.
- `sudo systemctl restart sss2-backend` — kiosk shows "Backend Disconnected" briefly,
  then reloads automatically.
- `sudo reboot` and `sudo poweroff` then power back — must return to the dashboard
  with no interaction.

## Troubleshooting

| Symptom | Check |
|--------|-------|
| Black screen, no browser | `journalctl -u sss2-kiosk -b` — usually cage seat perms; confirm `$APP_USER` is in `video render input tty seat` and re-login/reboot |
| `can0` missing | overlays in `/boot/firmware/config.txt`; `dmesg \| grep -i mcp2515`; HAT oscillator/interrupt pins |
| UI CAN buttons 500 | `sudo -n systemctl start can@can0` as the app user must work — check `/etc/sudoers.d/sss2-can` username/paths |
| "Backend Disconnected" forever | `journalctl -u sss2-backend -b`; did `deploy-pi.sh` build the UI into `app-ui/static/ui/`? |
| Chromium "restore pages" bar | handled by the profile scrub in `kiosk-chromium.sh`; clear `~/.config/sss2-kiosk` if it persists |

## Maintenance / getting out of the kiosk

The kiosk is a deliberate lock, with three ways out:

1. **On-screen Admin panel (PIN-gated).** Tap the **⚙** in the header (or press
   **Ctrl+Alt+A**), enter the admin PIN, then pick: Exit to Desktop, Exit to
   Console, Update & Restart, Restart GUI, Restart App, Reboot, Shut Down. Each
   destructive action asks for confirmation.
2. **Keyboard console:** **Ctrl+Alt+F2** switches to a login VT (the kiosk stays on
   tty1). Log in and run anything; **Ctrl+Alt+F1** returns to the kiosk.
3. **SSH** (enabled by setup): `sudo systemctl stop sss2-kiosk` → shell;
   `./scripts/deploy-pi.sh` to update; `sudo systemctl start sss2-kiosk` to return.

**Set the PIN** — edit `/etc/default/sss2-kiosk` (`SYSTEM_ADMIN_PIN=...`) and
`sudo systemctl restart sss2-backend`. An empty PIN disables the panel (fail-closed).

**How it stays safe:** the backend never holds broad root. Every privileged action
goes through one **root-owned** helper, `/usr/local/sbin/sss2-kiosk-admin`, allowed
by a single narrow sudoers rule ([deploy/sudoers/sss2-system](../deploy/sudoers/sss2-system)).
The API is on the LAN, so the PIN is required on every call. "Update & Restart" runs
[deploy/scripts/kiosk-update.sh](../deploy/scripts/kiosk-update.sh) detached (logs to
`/tmp/sss2-kiosk-update.log`) so it survives the restart it triggers.

> "Exit to Desktop" starts a display manager (lightdm/gdm/sddm) if one is installed;
> if the appliance is console-only it opens a login console instead. To return to the
> kiosk from the desktop/console: `sudo systemctl start sss2-kiosk`.

## Production notes

This appliance has **no authentication** and commands real hardware. Keep it on an
isolated bench/vehicle network. If remote access is ever needed, front it with a VPN
(e.g. Tailscale) rather than exposing port 8000/80 to the internet.

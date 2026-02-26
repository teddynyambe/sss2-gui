#!/usr/bin/env bash
set -euo pipefail

# === CONFIG (edit these two paths if needed) ===
SRC="/vm_shared/teddy/Projects/sss2-gui/ui"      # shared folder (Mac -> Kali)
DST="$HOME/sss2-gui-ui"                          # Kali local copy

echo "==> Syncing source to Kali local folder..."
echo "    SRC: $SRC/"
echo "    DST: $DST/"
mkdir -p "$DST"
rsync -a "$SRC/" "$DST/"

echo "==> Moving into local project folder..."
cd "$DST"

echo "==> Safety check: refuse to run if destination is on /vm_shared or /media/psf"
PWD_REAL="$(pwd -P)"
if [[ "$PWD_REAL" == /vm_shared/* || "$PWD_REAL" == /media/psf/* ]]; then
  echo "ERROR: Refusing to delete inside shared folder: $PWD_REAL"
  echo "Fix DST to a local path like \$HOME/sss2-gui-ui and try again."
  exit 1
fi

echo "==> Removing node_modules and package-lock.json in LOCAL copy..."
rm -rf node_modules package-lock.json

echo "==> Installing npm dependencies..."
npm install

echo "==> Done."
echo "Tip: run 'cd \"$DST\" && npm run dev' to start the dev server."

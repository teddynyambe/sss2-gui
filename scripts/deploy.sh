#!/bin/bash
#
# deploy.sh — run on your DEV machine (Mac).
# Commits local work and pushes it to the production GitHub repo
# (SystemsCyber/sss2-gui-v2, the "org" remote). The Raspberry Pi then runs
# scripts/deploy-pi.sh to pull + build + restart the services.
#
# Usage:
#   ./scripts/deploy.sh "commit message"     # commit staged+unstaged, then push
#   ./scripts/deploy.sh                       # push only (working tree must be clean)
#
set -euo pipefail

# ===== Config (override via env if needed) =====
ORG_REMOTE="${ORG_REMOTE:-org}"          # remote pointing at SystemsCyber/sss2-gui-v2
BRANCH="${BRANCH:-main}"

# Move to repo root (this script lives in scripts/)
cd "$(dirname "$0")/.."

echo "--------------------------------------"
echo "Deploying source -> $ORG_REMOTE/$BRANCH"
echo "--------------------------------------"

# Ensure the org remote exists and points where we expect
if ! git remote get-url "$ORG_REMOTE" >/dev/null 2>&1; then
  echo "ERROR: git remote '$ORG_REMOTE' not found."
  echo "Add it with:"
  echo "  git remote add $ORG_REMOTE https://github.com/SystemsCyber/sss2-gui-v2.git"
  exit 1
fi
echo "Remote: $(git remote get-url "$ORG_REMOTE")"

# Commit any local changes if a message was provided
MSG="${1:-}"
if [ -n "$(git status --porcelain)" ]; then
  if [ -z "$MSG" ]; then
    echo "ERROR: you have uncommitted changes but gave no commit message."
    echo "Run:  ./scripts/deploy.sh \"describe your change\""
    exit 1
  fi
  echo "==> Committing local changes..."
  git add -A
  git commit -m "$MSG"
fi

echo "==> Pushing $BRANCH to $ORG_REMOTE..."
git push "$ORG_REMOTE" "$BRANCH"

echo "--------------------------------------"
echo "Pushed. On the Raspberry Pi run:"
echo "    ./scripts/deploy-pi.sh"
echo "--------------------------------------"

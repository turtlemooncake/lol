#!/usr/bin/env bash
#
# Push local code to the Hetzner box and (re)build the engine container.
#
#   ./deploy/deploy.sh root@<server-ip>      # e.g. root@62.238.40.1
#
# Run from anywhere; paths are resolved relative to the repo root. Mirrors the
# manual first-deploy steps:
#   - rsync the working tree to /opt/lol (skipping venv/caches/secrets)
#   - rebuild + restart the container with the new code
#
# .env is deliberately NOT synced (it holds secrets and is gitignored). Copy it
# once by hand on first setup:
#   scp .env root@<server-ip>:/opt/lol/.env
# --delete won't remove it on re-syncs: excluded files are protected.

set -euo pipefail

TARGET="${1:?usage: deploy/deploy.sh user@host}"
REMOTE_DIR=/opt/lol
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> syncing $ROOT -> $TARGET:$REMOTE_DIR"
rsync -az --delete \
  --exclude '.git' --exclude '.env' \
  --exclude '__pycache__/' --exclude '*.pyc' \
  --exclude 'pyvenv/' --exclude '.venv/' --exclude 'venv/' \
  --exclude '*.egg-info/' --exclude 'local/' --exclude '.DS_Store' \
  "$ROOT/" "$TARGET:$REMOTE_DIR/"

echo "==> rebuilding + restarting container"
ssh "$TARGET" "cd $REMOTE_DIR && docker compose up -d --build && docker compose ps"

echo "==> done. tail logs with: ssh $TARGET 'cd $REMOTE_DIR && docker compose logs -f'"

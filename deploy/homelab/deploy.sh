#!/usr/bin/env bash
# Deploys the current working tree to a single Linux host (LXC / VM) reachable over SSH as root.
# Idempotent: the first run bootstraps the host, later runs only sync code and restart the service.
#
#   EXAMEN_DEPLOY_HOST=root@<host> deploy/homelab/deploy.sh
#
# Options (env vars):
#   SYNC_ENV=1        also copy ./.env (AWS credentials) to /opt/examen/.env (mode 600)
#   SKIP_UI_BUILD=1   reuse the existing src/web_ui/out build
#   BEE_BINARY=<path> Bee CLI binary to install as /usr/local/bin/bee
#                     (default: resources/bee-cli/dist/platforms/linux-x64/bee, copied only if missing remotely)
#
# Runbook: docs/11_homelab_test_deployment.md
set -euo pipefail

HOST="${EXAMEN_DEPLOY_HOST:?set EXAMEN_DEPLOY_HOST, e.g. root@examen.lan}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BEE_BINARY="${BEE_BINARY:-$ROOT/resources/bee-cli/dist/platforms/linux-x64/bee}"
cd "$ROOT"

if [ "${SKIP_UI_BUILD:-0}" != 1 ]; then
  ./scripts/build_ui.sh
fi
[ -f src/web_ui/out/index.html ] || { echo "Dashboard build missing (src/web_ui/out)"; exit 1; }

echo "==> Bootstrapping $HOST (idempotent)"
ssh "$HOST" 'set -e
  export DEBIAN_FRONTEND=noninteractive
  command -v rsync >/dev/null || { apt-get update -qq && apt-get install -y -qq rsync ca-certificates curl sqlite3 jq >/dev/null; }
  id examen >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/examen --shell /bin/bash examen
  install -d -o examen -g examen /opt/examen
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
  cd /var/lib/examen && sudo -u examen -H uv python install 3.12 >/dev/null'

if ! ssh "$HOST" 'command -v bee >/dev/null' || [ -n "${BEE_BINARY_FORCE:-}" ]; then
  echo "==> Installing Bee CLI"
  scp -q "$BEE_BINARY" "$HOST:/usr/local/bin/bee"
  ssh "$HOST" 'chmod 755 /usr/local/bin/bee'
fi

echo "==> Syncing code"
rsync -az --delete \
  --exclude '.git/' --exclude '.venv/' --exclude '.direnv/' --exclude '.bee-spike/' --exclude '.env' \
  --exclude 'resources/bee-cli/' --exclude 'resources/agentcore-samples/' \
  --exclude 'src/web_ui/node_modules/' --exclude 'src/web_ui/.next/' \
  --exclude '__pycache__/' --exclude '.pytest_cache/' --exclude '*.db' --exclude 'examen.db.*' \
  --exclude '/data/' \
  ./ "$HOST:/opt/examen/"

if [ "${SYNC_ENV:-0}" = 1 ]; then
  echo "==> Copying .env"
  scp -q .env "$HOST:/opt/examen/.env"
fi

echo "==> Installing dependencies and restarting the service"
ssh "$HOST" 'set -e
  chown -R examen:examen /opt/examen
  [ -f /opt/examen/.env ] && chmod 600 /opt/examen/.env
  cd /opt/examen
  [ -x .venv/bin/python ] || sudo -u examen -H uv venv --python 3.12 .venv -q
  sudo -u examen -H uv pip install -q --python .venv/bin/python -r requirements.txt
  install -m 644 deploy/homelab/examen.service /etc/systemd/system/examen.service
  systemctl daemon-reload
  systemctl enable -q examen
  systemctl restart examen
  sleep 4
  systemctl is-active examen
  curl -fsS http://127.0.0.1:8000/api/orchestrator/status | head -c 300; echo
  sudo -u examen -H bee status | tail -1'

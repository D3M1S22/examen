#!/usr/bin/env bash
# Pulls the deployed branch on the server and applies it. Runs as root on the server
# (systemd `examen-update.timer` every 5 minutes, or by hand: `examen-update [--force]`).
#
# - nothing to do when origin/<branch> has not moved (unless --force);
# - reinstalls Python deps only if requirements.txt / pyproject.toml changed;
# - rebuilds the dashboard only if src/web_ui/ changed (or the build is missing);
# - reinstalls the systemd units if they changed;
# - restarts the service and rolls back to the previous commit if the health check fails.
#
# Runbook: docs/11_homelab_test_deployment.md
set -euo pipefail

APP_DIR="${EXAMEN_APP_DIR:-/opt/examen}"
BRANCH="${EXAMEN_BRANCH:-main}"
HEALTH_URL="${EXAMEN_HEALTH_URL:-http://127.0.0.1:8000/api/health}"  # unauthenticated liveness probe

as_app() { (cd "$APP_DIR" && sudo -u examen -H "$@"); }

healthy() {
  for _ in $(seq 1 20); do
    curl -fsS -m 3 "$HEALTH_URL" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

apply() {
  local changed="$1" force="$2"
  if [ "$force" = 1 ] || grep -qE '^(requirements\.txt|pyproject\.toml)$' <<<"$changed"; then
    echo "==> Python dependencies"
    as_app uv pip install -q --python .venv/bin/python -r requirements.txt
  fi
  if [ "$force" = 1 ] || grep -q '^src/web_ui/' <<<"$changed" || [ ! -f "$APP_DIR/src/web_ui/out/index.html" ]; then
    echo "==> Dashboard build"
    (cd "$APP_DIR/src/web_ui" && sudo -u examen -H bun install --frozen-lockfile >/dev/null && sudo -u examen -H bun run build >/dev/null)
  fi
  if [ "$force" = 1 ] || grep -q '^deploy/homelab/.*\.\(service\|timer\)$' <<<"$changed"; then
    echo "==> systemd units"
    install -m 644 "$APP_DIR/deploy/homelab/examen.service" /etc/systemd/system/examen.service
    install -m 644 "$APP_DIR/deploy/homelab/examen-update.service" /etc/systemd/system/examen-update.service
    install -m 644 "$APP_DIR/deploy/homelab/examen-update.timer" /etc/systemd/system/examen-update.timer
    systemctl daemon-reload
  fi
  echo "==> Restart"
  systemctl restart examen
  healthy
}

main() {
  local force=0
  [ "${1:-}" = "--force" ] && force=1

  exec 9>/run/lock/examen-update.lock
  flock -n 9 || { echo "Another update is running"; exit 0; }

  as_app git fetch -q origin "$BRANCH"
  local old new
  old="$(as_app git rev-parse HEAD)"
  new="$(as_app git rev-parse "origin/$BRANCH")"
  if [ "$old" = "$new" ] && [ "$force" = 0 ]; then
    echo "Up to date at ${new:0:7}"
    exit 0
  fi

  local changed
  changed="$(as_app git diff --name-only "$old" "$new")"
  echo "==> ${old:0:7} -> ${new:0:7} ($(wc -l <<<"$changed") files)"
  as_app git reset -q --hard "$new"

  if apply "$changed" "$force"; then
    echo "Deployed ${new:0:7}: $(as_app git log -1 --format=%s)"
    exit 0
  fi

  echo "Health check failed: rolling back to ${old:0:7}" >&2
  as_app git reset -q --hard "$old"
  apply "$changed" 1 || true
  exit 1
}

# The whole file is parsed before main runs, so `git reset` can safely replace this script.
main "$@"
exit

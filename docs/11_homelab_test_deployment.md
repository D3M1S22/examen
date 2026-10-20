# 11 — Homelab Test Deployment (single LXC, before AWS)

> **Status:** live since 2026-10-19
> **Purpose:** a long-running test instance with the real Bee account and real Bedrock models, before the AWS deployment of [06_aws_cloud_deployment_architecture.md](06_aws_cloud_deployment_architecture.md).
> **Files:** [deploy/homelab/update.sh](../deploy/homelab/update.sh) (pull `main`), [deploy/homelab/deploy.sh](../deploy/homelab/deploy.sh) (push a working copy / bootstrap), [examen.service](../deploy/homelab/examen.service), [examen-update.service](../deploy/homelab/examen-update.service) + [.timer](../deploy/homelab/examen-update.timer)

---

## 1. Current instance

| Item | Value |
|---|---|
| Host | Proxmox homelab, container **CT 147** (`examen`), Ubuntu 22.04, 2 vCPU, 2 GB RAM, 16 GB rootfs on `SSD2`, `onboot=1` |
| LAN address | `192.168.1.192`, service on port `8000` |
| URL | `http://examen.deggio.local/` (Pi-hole record → Nginx Proxy Manager → `192.168.1.192:8000`) |
| Endpoints | Dashboard `/`, Echo Show `/ext-app/`, MCP `/mcp`, REST `/api/*`, SSE `/api/events` |
| Service | systemd `examen.service`, user `examen`, code in `/opt/examen` (git checkout of `origin/main`), venv `/opt/examen/.venv` (uv, Python 3.12); Bun 1.4 for dashboard builds |
| Bee CLI | `/usr/local/bin/bee` (0.7.3); token in `/var/lib/examen/.bee/` (the service user's home) |
| Secrets | `/opt/examen/.env` (mode 600, owner `examen`): AWS credentials and model settings |
| Data | SQLite `/opt/examen/examen.db` |
| Time zone | `Europe/Rome` (same as the Bee account: EXAMEN uses naive local times) |
| SSH | key-only root login (`PermitRootLogin prohibit-password`, no passwords) |

The reverse proxy disables buffering (`proxy_buffering off`, 1 h read timeout), which is required for `/api/events` and the MCP streamable HTTP transport.

---

## 2. Updates: the server tracks `main`

`/opt/examen` is a git checkout of **`origin/main`**, read through a read-only GitHub deploy key of the `examen` user (`/var/lib/examen/.ssh/id_ed25519`). Pushing to `main` is enough:

| What | How |
|---|---|
| Automatic | `examen-update.timer` runs [deploy/homelab/update.sh](../deploy/homelab/update.sh) every 5 minutes |
| Manual | `ssh root@192.168.1.192 examen-update` (`--force` reinstalls deps, rebuilds the UI and the units) |
| Logs | `ssh root@192.168.1.192 'journalctl -u examen-update -n 50'` |
| Pause | `systemctl stop examen-update.timer` (e.g. while testing a working copy, below) |

`update.sh` does nothing if `origin/main` has not moved. Otherwise it hard-resets to it, reinstalls Python deps only when `requirements.txt` / `pyproject.toml` changed, rebuilds the dashboard (Bun) only when `src/web_ui/` changed, reinstalls the systemd units when they changed, restarts `examen` and waits for `/api/health` (unauthenticated; `/api/status` needs a session since multi-user). If the health check fails it rolls back to the previous commit. `.env`, `.venv`, `examen.db` and `src/web_ui/out` are untracked and survive updates.

**Testing uncommitted work:** `EXAMEN_DEPLOY_HOST=root@192.168.1.192 deploy/homelab/deploy.sh` still pushes the local working copy (rsync, `.git` untouched). Stop the timer first: the next update resets the server to `main`.

### 2.1 First-time setup of a new server

1. `EXAMEN_DEPLOY_HOST=root@<host> SYNC_ENV=1 deploy/homelab/deploy.sh`: user, uv/Python 3.12, Bee binary, venv, service.
2. Deploy key: `sudo -u examen -H ssh-keygen -t ed25519 -N "" -f /var/lib/examen/.ssh/id_ed25519`, add the public key to the GitHub repository (*Settings → Deploy keys*, read-only), `ssh-keyscan -t ed25519 github.com` into `/var/lib/examen/.ssh/known_hosts`.
3. Turn `/opt/examen` into a checkout: `git init`, `git remote add origin git@github.com:<owner>/<repo>.git`, `git fetch origin main`, `git reset --hard origin/main` (as `examen`).
4. Install Bun (`curl -fsSL https://bun.sh/install | BUN_INSTALL=/usr/local bash`), link `examen-update` → `/opt/examen/deploy/homelab/update.sh`, install and enable `examen-update.timer`, run `examen-update --force`.

## 3. Accounts and Bee login on the server

Since 2026-10-20 the instance is multi-user ([13_multi_user_accounts.md](13_multi_user_accounts.md)): each person creates an account in the dashboard and pairs **their own** Bee from *Account → Bee device* by scanning a QR code. Tokens and data live under `/var/lib/examen/data/users/<id>/` (`EXAMEN_DATA_DIR`, set in the systemd unit); nobody logs in to Bee from the shell any more. The redeploy script never touches `/data/` and the old single-user token in `/var/lib/examen/.bee/` is no longer used.

```bash
# Move the data collected before accounts existed into the owner's account (once):
ssh root@192.168.1.192 'cd /opt/examen && sudo -u examen -H EXAMEN_DATA_DIR=/var/lib/examen/data \
  .venv/bin/python scripts/manage_users.py claim-legacy-db --email <owner email> --db /opt/examen/examen.db'
# Password reset (no email service yet):
ssh -t root@192.168.1.192 'cd /opt/examen && sudo -u examen -H EXAMEN_DATA_DIR=/var/lib/examen/data \
  .venv/bin/python scripts/manage_users.py reset-password --email <email>'
```

Add the LAN host name to `MCP_ALLOWED_HOSTS` in `/opt/examen/.env` (`examen.deggio.local,examen.deggio.local:*`), otherwise `/mcp` answers `421` behind Nginx Proxy Manager. With `AUTH_ENABLED=false` the old single-user behaviour (one shell `bee login` for the host) still applies.

## 4. Operations

```bash
ssh root@192.168.1.192 'journalctl -u examen -f'                          # logs
curl -s http://examen.deggio.local/api/orchestrator/status | jq             # stream, transport, speaker tags, location
curl -s http://examen.deggio.local/api/backfill/coverage | jq '.gaps'
ssh root@192.168.1.192 'systemctl stop examen && rm /opt/examen/examen.db && systemctl start examen'   # reset data
```

Through MCP from an agent: `get_lxc_service_logs(vmid=147, service_name="examen")`, `exec_lxc_command(vmid=147, ...)`.

---

## 5. Known limitations of the test instance

- Plain HTTP on the LAN (like the other `*.deggio.local` services): no TLS, so session cookies and MCP tokens travel in clear text on the LAN. Do not expose it publicly; the AWS deployment adds CloudFront/TLS.
- Each paired user runs their own `bee proxy` + stream: watch memory on the 2 GB container.

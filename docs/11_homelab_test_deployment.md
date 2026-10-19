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
| Bee CLI | `/usr/local/bin/bee` (0.7.3); **one token per EXAMEN user** in `/var/lib/examen/data/users/<user_id>/bee/` (mode 0700, `BEE_CONFIG_DIR` + `BEE_FORCE_FILE_STORE=1`) |
| Secrets | `/opt/examen/.env` (mode 600, owner `examen`): AWS credentials and model settings |
| Data | `/var/lib/examen/data/system.db` (users, sessions, tokens, Bee links) and one SQLite file per user in `/var/lib/examen/data/users/<user_id>/examen.db` (`EXAMEN_DATA_DIR`, set by `examen.service`) |
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

`update.sh` does nothing if `origin/main` has not moved. Otherwise it hard-resets to it, reinstalls Python deps only when `requirements.txt` / `pyproject.toml` changed, rebuilds the dashboard (Bun) only when `src/web_ui/` changed, reinstalls the systemd units when they changed, restarts `examen` and waits for `/api/status`. If the health check fails it rolls back to the previous commit. `.env`, `.venv`, `examen.db` and `src/web_ui/out` are untracked and survive updates.

**Testing uncommitted work:** `EXAMEN_DEPLOY_HOST=root@192.168.1.192 deploy/homelab/deploy.sh` still pushes the local working copy (rsync, `.git` untouched). Stop the timer first: the next update resets the server to `main`.

### 2.1 First-time setup of a new server

1. `EXAMEN_DEPLOY_HOST=root@<host> SYNC_ENV=1 deploy/homelab/deploy.sh`: user, uv/Python 3.12, Bee binary, venv, service.
2. Deploy key: `sudo -u examen -H ssh-keygen -t ed25519 -N "" -f /var/lib/examen/.ssh/id_ed25519`, add the public key to the GitHub repository (*Settings → Deploy keys*, read-only), `ssh-keyscan -t ed25519 github.com` into `/var/lib/examen/.ssh/known_hosts`.
3. Turn `/opt/examen` into a checkout: `git init`, `git remote add origin git@github.com:<owner>/<repo>.git`, `git fetch origin main`, `git reset --hard origin/main` (as `examen`).
4. Install Bun (`curl -fsSL https://bun.sh/install | BUN_INSTALL=/usr/local bash`), link `examen-update` → `/opt/examen/deploy/homelab/update.sh`, install and enable `examen-update.timer`, run `examen-update --force`.

## 3. Accounts and Bee login (multi-user)

Every person signs in with their own EXAMEN account and links **their own** Bee account from the dashboard ([multi_user/](next_steps/multi_user/00_overview.md)):

1. The first start with an empty user table creates the admin named by `EXAMEN_BOOTSTRAP_ADMIN` in `/opt/examen/.env`. Without `EXAMEN_BOOTSTRAP_ADMIN_PASSWORD`, a one-time password is printed once: `journalctl -u examen | grep "Bootstrap admin"`.
2. The admin creates the other accounts in *Account → Accounts (admin)*; each new user gets a one-time password.
3. Each user opens *Account → Your Bee account → Connect Bee*, opens the link and approves it in the Bee app; the dashboard polls until the link is `linked` and starts that user's live ingestion.
4. MCP clients (Alexa+ dev skill, Claude Desktop, …) use a personal access token from *Account → MCP access tokens* (`Authorization: Bearer exm_pat_…`).

Signing out ends only the browser session; Bee keeps streaming for that user. *Disconnect Bee* and *Erase my data* act on the signed-in user only.

---

## 4. Operations

```bash
ssh root@192.168.1.192 'journalctl -u examen -f'                          # logs
curl -s http://examen.deggio.local/api/health                               # liveness (no auth)
T=exm_pat_…                                                                  # a personal access token
curl -s -H "Authorization: Bearer $T" http://examen.deggio.local/api/orchestrator/status | jq   # that user's stream
curl -s -H "Authorization: Bearer $T" http://examen.deggio.local/api/backfill/coverage | jq '.gaps'
ssh root@192.168.1.192 'systemctl stop examen && rm -r /var/lib/examen/data && systemctl start examen'   # wipe ALL users
```

Through MCP from an agent: `get_lxc_service_logs(vmid=147, service_name="examen")`, `exec_lxc_command(vmid=147, ...)`.

---

## 5. Known limitations of the test instance

- Plain HTTP on the LAN (like the other `*.deggio.local` services): session cookies and tokens travel unencrypted. Fine on a trusted LAN; add an NPM certificate and `AUTH_COOKIE_SECURE=true` before inviting people from other networks (open question Q3 of [multi_user/05](next_steps/multi_user/05_implementation_plan_and_testing.md)). Do not expose it publicly.
- `MAX_ACTIVE_USERS` (default 5) live Bee streams on 2 GB of RAM: each one runs a private `bee proxy` (to be measured, MU-V2).

---

## 6. Rolling out multi-user on an existing instance

Done once, when the `sessions` work reaches `main` (the server tracks `main`):

1. `ssh root@192.168.1.192 'systemctl stop examen-update.timer examen'`.
2. Add `EXAMEN_BOOTSTRAP_ADMIN=<username>` (and optionally `EXAMEN_BOOTSTRAP_ADMIN_PASSWORD`) to `/opt/examen/.env`.
3. `ssh root@192.168.1.192 'EXAMEN_HEALTH_URL=http://127.0.0.1:8000/api/health examen-update --force'`: pulls `main`, installs `argon2-cffi`, rebuilds the dashboard, installs the new unit (`EXAMEN_DATA_DIR=/var/lib/examen/data`), restarts and checks `/api/health`.
4. Optional, to keep the single-tenant data and Bee token: `systemctl stop examen && cd /opt/examen && sudo -u examen -H EXAMEN_DATA_DIR=/var/lib/examen/data .venv/bin/python scripts/migrate_to_multi_user.py --owner <username> --db /opt/examen/examen.db --bee-dir /var/lib/examen/.bee && systemctl start examen`, then *Connect Bee* once to verify the migrated token.
5. `systemctl start examen-update.timer`.

The instance already has a safety net: `/etc/systemd/system/examen-update.service.d/health.conf` sets `EXAMEN_HEALTH_URL=http://127.0.0.1:8000/` (the dashboard, public before and after the change), so even an unattended update does not loop on rollbacks. Remove it after the rollout.

Why steps 1 and 3 matter: the `update.sh` that runs is the one already on the server, which checks `/api/status` by default. That endpoint now answers `401`, so without `EXAMEN_HEALTH_URL` the update would roll itself back. Later updates use the new script (`/api/health`).

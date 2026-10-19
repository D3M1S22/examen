# 11 — Homelab Test Deployment (single LXC, before AWS)

> **Status:** live since 2026-10-19
> **Purpose:** a long-running test instance with the real Bee account and real Bedrock models, before the AWS deployment of [06_aws_cloud_deployment_architecture.md](06_aws_cloud_deployment_architecture.md).
> **Files:** [deploy/homelab/deploy.sh](../deploy/homelab/deploy.sh), [deploy/homelab/examen.service](../deploy/homelab/examen.service)

---

## 1. Current instance

| Item | Value |
|---|---|
| Host | Proxmox homelab, container **CT 147** (`examen`), Ubuntu 22.04, 2 vCPU, 2 GB RAM, 16 GB rootfs on `SSD2`, `onboot=1` |
| LAN address | `192.168.1.192`, service on port `8000` |
| URL | `http://examen.deggio.local/` (Pi-hole record → Nginx Proxy Manager → `192.168.1.192:8000`) |
| Endpoints | Dashboard `/`, Echo Show `/ext-app/`, MCP `/mcp`, REST `/api/*`, SSE `/api/events` |
| Service | systemd `examen.service`, user `examen`, code in `/opt/examen`, venv `/opt/examen/.venv` (uv, Python 3.12) |
| Bee CLI | `/usr/local/bin/bee` (0.7.3); token in `/var/lib/examen/.bee/` (the service user's home) |
| Secrets | `/opt/examen/.env` (mode 600, owner `examen`): AWS credentials and model settings |
| Data | SQLite `/opt/examen/examen.db` |
| Time zone | `Europe/Rome` (same as the Bee account: EXAMEN uses naive local times) |
| SSH | key-only root login (`PermitRootLogin prohibit-password`, no passwords) |

The reverse proxy disables buffering (`proxy_buffering off`, 1 h read timeout), which is required for `/api/events` and the MCP streamable HTTP transport.

---

## 2. Redeploy from a workstation

```bash
EXAMEN_DEPLOY_HOST=root@192.168.1.192 deploy/homelab/deploy.sh             # build UI, sync code, restart
EXAMEN_DEPLOY_HOST=root@192.168.1.192 SYNC_ENV=1 deploy/homelab/deploy.sh  # also push ./.env
EXAMEN_DEPLOY_HOST=root@192.168.1.192 SKIP_UI_BUILD=1 deploy/homelab/deploy.sh
```

The script is idempotent. On a fresh Ubuntu/Debian host it also creates the `examen` user, installs `uv` + Python 3.12, copies the Bee binary (`resources/bee-cli/dist/platforms/linux-x64/bee`, see [AGENTS.MD](../AGENTS.MD) §7) and installs the systemd unit. It syncs the **working tree**, uncommitted changes included, and never copies `.git`, `.venv`, `.bee-spike/` (personal captures) or databases.

Note: `scripts/build_ui.sh` may rewrite `src/web_ui/bun.lock` with an older Bun; revert it with `git checkout src/web_ui/bun.lock` if the change is only the lockfile version.

---

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

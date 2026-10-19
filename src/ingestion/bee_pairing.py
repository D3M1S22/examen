"""Per-user Bee pairing through bee-cli's app-pairing flow (docs/13_multi_user_accounts.md §4).

How bee-cli logs in (resources/bee-cli/sources/commands/login/index.ts):

1. ``bee login`` asks the Bee API for a pairing request and prints
   ``Authentication link: https://bee.computer/connect#<request id>`` (valid ~5 minutes).
2. The device owner opens the link (or scans its QR code) and approves in the Bee app.
3. ``bee login`` polls every 2 s, decrypts the token and saves it in the token store.

``bee login --no-wait`` stops after step 1, and re-running it only re-prints the link: it never
completes the pairing. So EXAMEN starts a *blocking* ``bee login`` in the background for the user,
reads the link from its output for the dashboard (shown as a QR code), and waits for the process to
exit. Every call runs with the user's private ``BEE_CONFIG_DIR`` and ``BEE_FORCE_FILE_STORE=1``
(src/core/tenancy.py), so the token lands in that user's folder and nowhere else.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from typing import Any, Awaitable, Callable, Dict, Optional

from src.core.tenancy import bee_subprocess_env, get_tenant_id

logger = logging.getLogger("examen.ingestion.bee_pairing")

_LINK_RE = re.compile(r"Authentication link:\s*(https://\S+)")
_ALREADY_RE = re.compile(r"already connected to Bee as (.*?)\.", re.IGNORECASE)
_SUCCESS_RE = re.compile(r"connected to the Bee account of (.*?)\.", re.IGNORECASE)

# The Bee API expires pairing requests after ~5 minutes; the process is killed a little later.
PAIRING_TIMEOUT_SECONDS = 330.0
LINK_WAIT_SECONDS = 25.0


class BeePairing:
    """State machine: idle → pending (link shown) → connected | expired | failed."""

    def __init__(self, user_id: Optional[str] = None,
                 on_connected: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None,
                 build_cmd: Optional[Callable[[list], list]] = None):
        self.user_id = user_id if user_id is not None else get_tenant_id()
        self.on_connected = on_connected
        self._build_cmd = build_cmd
        self.status: str = "idle"
        self.pairing_url: Optional[str] = None
        self.account: Optional[str] = None
        self.error: Optional[str] = None
        self.started_at: Optional[float] = None
        self.process: Optional[asyncio.subprocess.Process] = None
        self._task: Optional[asyncio.Task] = None
        self._link_ready: Optional[asyncio.Event] = None

    def _cmd(self, args: list) -> list:
        if self._build_cmd is not None:
            return self._build_cmd(args)
        from src.ingestion.stream_convo import BeeClient

        return BeeClient()._build_cmd(args)

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    def snapshot(self) -> Dict[str, Any]:
        expires_in = None
        if self.status == "pending" and self.started_at is not None:
            expires_in = max(0, int(PAIRING_TIMEOUT_SECONDS - (time.monotonic() - self.started_at)))
        return {
            "status": self.status,
            "connected": self.status == "connected",
            "pairing_url": self.pairing_url if self.status == "pending" else None,
            "expires_in_seconds": expires_in,
            "account": self.account,
            "error": self.error,
        }

    async def start(self) -> Dict[str, Any]:
        """Starts a pairing (or returns the one in progress) and waits until its link is known."""
        if self.running and self.status == "pending" and self.pairing_url:
            return self.snapshot()
        await self.cancel()
        self.status, self.pairing_url, self.error, self.account = "starting", None, None, None
        self.started_at = time.monotonic()
        self._link_ready = asyncio.Event()
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self._cmd(["login"]),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=bee_subprocess_env(self.user_id),
            )
        except OSError as e:
            self.status, self.error = "failed", f"Bee CLI is not available on the server ({e.__class__.__name__})."
            return self.snapshot()
        self._task = asyncio.create_task(self._watch())
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._link_ready.wait(), timeout=LINK_WAIT_SECONDS)
        if self.status == "starting":
            self.status, self.error = "failed", "Bee did not return a pairing link in time. Try again."
            await self.cancel(keep_status=True)
        return self.snapshot()

    async def _watch(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        output: list[str] = []
        try:
            async def _read() -> None:
                while True:
                    raw = await self.process.stdout.readline()
                    if not raw:
                        return
                    line = raw.decode("utf-8", "replace").strip()
                    output.append(line)
                    link = _LINK_RE.search(line)
                    if link and self.status == "starting":
                        self.pairing_url, self.status = link.group(1), "pending"
                        self._link_ready.set()
                    for rx in (_ALREADY_RE, _SUCCESS_RE):
                        m = rx.search(line)
                        if m:
                            self.account = m.group(1).strip()

            await asyncio.wait_for(_read(), timeout=PAIRING_TIMEOUT_SECONDS)
            code = await self.process.wait()
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                self.process.kill()
            self.status, self.error = "expired", "The pairing link expired. Start again."
            self._link_ready.set()
            return
        except asyncio.CancelledError:
            raise
        # `bee login` exits 0 only after saving the token (or when already logged in); an expired or
        # rejected pairing throws and exits non-zero.
        if code == 0:
            self.status, self.pairing_url = "connected", None
            logger.info("Bee pairing completed for a user")  # no account name in logs
            if self.on_connected is not None:
                try:
                    result = self.on_connected(self.snapshot())
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning(f"Post-pairing hook failed: {e}")
        else:
            tail = " ".join(output)[-200:].lower()
            self.status = "expired" if "expired" in tail else "failed"
            self.error = "The pairing link expired. Start again." if self.status == "expired" else "Bee pairing failed."
        self._link_ready.set()

    async def cancel(self, keep_status: bool = False) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._task = None
        if self.running:
            with contextlib.suppress(ProcessLookupError):
                self.process.kill()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.process.wait(), timeout=5)
        self.process = None
        if not keep_status and self.status in ("starting", "pending"):
            self.status, self.pairing_url = "idle", None


async def bee_logout(user_id: Optional[str] = None, build_cmd: Optional[Callable[[list], list]] = None) -> bool:
    """Clears one user's bee-cli login (their folder only; other users are untouched)."""
    uid = user_id if user_id is not None else get_tenant_id()
    if build_cmd is None:
        from src.ingestion.stream_convo import BeeClient

        build_cmd = BeeClient()._build_cmd
    try:
        process = await asyncio.create_subprocess_exec(
            *build_cmd(["logout"]), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            env=bee_subprocess_env(uid),
        )
        await asyncio.wait_for(process.wait(), timeout=15)
        return process.returncode == 0
    except Exception as e:
        logger.warning(f"bee logout failed: {e.__class__.__name__}")
        return False

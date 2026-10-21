"""Bee CLI client: real-time event stream, location probe and binary resolution.

The payload shapes handled here are the ones observed on a real account (docs/10_bee_cli_reference.md),
not the ones of the official docs: `new-utterance` has no speaker, ISO `spoken_at` and relative
`start`/`end` seconds; speaker identity arrives as `tagged-utterance`; `update-utterance` does not exist.

Two stream transports (``BEE_STREAM_TRANSPORT``):
- ``proxy`` (default): raw SSE from ``/v1/stream`` through a private ``bee proxy`` on 127.0.0.1 (TCP:
  with ``--socket`` the proxy ignores ``--idle-timeout`` and Bun closes the stream after 10 s of idle).
  Server pings (every 30 s) are visible, so a stalled connection is detected within
  ``BEE_STREAM_PING_TIMEOUT_SECONDS`` and silence never looks like a dead stream.
- ``cli``: ``bee stream --json``. It drops pings, so liveness is "the process is still running".
"""

import asyncio
import contextlib
import json
import os
import platform
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple

from src.core.config import settings
from src.core.tenancy import bee_subprocess_env
from src.ingestion.debug import Debug

# Consecutive proxy failures after which the stream falls back to `bee stream --json`
PROXY_MAX_FAILURES = 3
# While on the CLI fallback, the proxy transport is tried again after this long
PROXY_RETRY_AFTER_SECONDS = 600.0
PROXY_START_TIMEOUT_SECONDS = 15.0
# Bun caps `bee proxy --idle-timeout` at 255 s; pings (30 s) keep the stream below it
PROXY_IDLE_TIMEOUT_SECONDS = 255
_PROXY_ADDRESS_RE = re.compile(r"Proxy listening on (http://\S+)")


def normalize_bee_time(value) -> Optional[str]:
    """Converts a Bee time value (epoch seconds/milliseconds or ISO string) to a local ISO string."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000.0 if value > 1e11 else float(value)
        return datetime.fromtimestamp(seconds).isoformat()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.isoformat()


def duration_ms(start: Any, end: Any) -> Optional[int]:
    """Utterance duration from Bee `start`/`end` (relative seconds with an unknown origin)."""
    if isinstance(start, bool) or isinstance(end, bool):
        return None
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end < start:
        return None
    return int(round((end - start) * 1000))


def _str_id(value: Any) -> str:
    return "" if value is None else str(value)


def parse_bee_payload(data: Dict[str, Any], received_at: str) -> Dict[str, Any]:
    """Maps one Bee stream payload (the SSE ``data`` object) to an EXAMEN stream event.

    Unknown payloads become ``stream-alive``: they still prove that the connection works.
    """
    msg_type = data.get("type") or data.get("event")

    if msg_type == "new-utterance":
        utt = data.get("utterance") if isinstance(data.get("utterance"), dict) else {}
        return {
            "event": "new-utterance",
            "data": {
                "id": _str_id(utt.get("id") or data.get("id")),
                "text": utt.get("text") or data.get("text") or "",
                # Not in the real payload (identity comes from tagged-utterance); kept for other sources
                "speaker": utt.get("speaker") or data.get("speaker"),
                "conversation_uuid": data.get("conversation_uuid") or data.get("conversation_id") or "default_session",
                # Receive time is captured before screening/queueing; spoken_at is the real speech time
                "received_at": received_at,
                "spoken_at": normalize_bee_time(utt.get("spoken_at") or data.get("spoken_at")),
                "duration_ms": duration_ms(utt.get("start"), utt.get("end")),
            },
        }
    if msg_type == "tagged-utterance":
        return {
            "event": "tagged-utterance",
            "data": {
                "utterance_id": _str_id(data.get("utterance_id")),
                "person_id": data.get("person_id"),
                "person_first_name": data.get("person_first_name"),
                "speaker_score": data.get("speaker_score"),
                "conversation_uuid": data.get("conversation_uuid"),
            },
        }
    if msg_type == "new-utterance-chunks":
        utterance_ids: List[str] = []
        for chunk in data.get("chunks") or []:
            if isinstance(chunk, dict):
                utterance_ids.extend(_str_id(u) for u in chunk.get("utterances") or [])
        return {
            "event": "new-utterance-chunks",
            "data": {
                "conversation_id": data.get("conversation_id"),
                "transcription_id": data.get("transcription_id"),
                "utterance_ids": utterance_ids,
            },
        }
    if msg_type == "update-location":
        loc = data.get("location") or (data.get("data") or {}).get("location") or {}
        return {"event": "update-location", "data": loc}
    if msg_type in ("new-conversation", "update-conversation", "update-conversation-summary", "delete-conversation"):
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        return {"event": msg_type, "data": payload}
    if msg_type == "connected" or (not msg_type and set(data.keys()) == {"timestamp"}):
        return {"event": "stream-connected", "data": data}
    if not msg_type and isinstance(data.get("conversation"), dict):
        # Payload without a type: detect conversation events structurally
        conv = data["conversation"]
        inferred = "update-conversation" if (conv.get("short_summary") or conv.get("title")) else "new-conversation"
        return {"event": inferred, "data": data}
    if not msg_type and "conversation_id" in data and "short_summary" in data:
        return {"event": "update-conversation-summary", "data": data}
    return {"event": "stream-alive", "data": {}}


class SseFrameParser:
    """Incremental parser of SSE lines (``retry:``, ``event:``, multi-line ``data:``, ``: ping`` comments)."""

    def __init__(self):
        self._event: Optional[str] = None
        self._data: List[str] = []

    def feed(self, line: str) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
        """Returns ``("ping", None, None)`` for a comment, ``("event", name, data)`` when a frame ends."""
        line = line.rstrip("\r")
        if line.startswith(":"):
            return ("ping", None, None)
        if line == "":
            if not self._data and self._event is None:
                return None
            frame = ("event", self._event, "\n".join(self._data) if self._data else None)
            self._event, self._data = None, []
            return frame
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            self._event = value
        elif field == "data":
            self._data.append(value)
        return None  # retry / id / unknown fields


def get_bee_binary_path() -> Optional[str]:
    """Resolves the best available Bee CLI executable path.

    Checks:
    1. System PATH ('bee')
    2. Local precompiled platform binary in resources/bee-cli/dist/platforms/
    3. resources/bee-cli/bin/bee.js (if bun/node is available)
    """
    which_bee = shutil.which("bee")
    if which_bee:
        return which_bee

    sys_name = platform.system().lower()
    machine = platform.machine().lower()
    base_dir = Path(__file__).resolve().parent.parent.parent

    candidate = None
    if sys_name == "darwin":
        if machine in ("arm64", "aarch64"):
            candidate = base_dir / "resources" / "bee-cli" / "dist" / "platforms" / "mac-arm64" / "bee"
        else:
            candidate = base_dir / "resources" / "bee-cli" / "dist" / "platforms" / "mac-x64" / "bee"
    elif sys_name == "linux":
        if machine in ("arm64", "aarch64"):
            candidate = base_dir / "resources" / "bee-cli" / "dist" / "platforms" / "linux-arm64" / "bee"
        else:
            candidate = base_dir / "resources" / "bee-cli" / "dist" / "platforms" / "linux-x64" / "bee"
    elif sys_name == "windows":
        candidate = base_dir / "resources" / "bee-cli" / "dist" / "platforms" / "windows-x64" / "bee.exe"

    if candidate and candidate.exists() and os.access(candidate, os.X_OK):
        return str(candidate)

    js_candidate = base_dir / "resources" / "bee-cli" / "bin" / "bee.js"
    if js_candidate.exists():
        return str(js_candidate)

    return None


class BeeStreamTimeout(Exception):
    """No SSE frame (not even a ping) for ``BEE_STREAM_PING_TIMEOUT_SECONDS``."""


class BeeProxyError(RuntimeError):
    """The private `bee proxy` could not be started or answered with an error."""


def default_http_transport(base_url: str):
    import httpx

    return httpx.AsyncHTTPTransport()


class BeeProxy(Debug):
    """Private `bee proxy` subprocess on 127.0.0.1: injects the Bee token for raw /v1 HTTP calls."""

    def __init__(self, build_cmd: Callable[[List[str]], List[str]], port: Optional[int] = None,
                 debug_mode: str = "none", env: Optional[Dict[str, str]] = None):
        super().__init__(debug_mode=debug_mode, sector_name="BEE")
        self.build_cmd = build_cmd
        self.env = env
        self.port = settings.bee_proxy_port if port is None else port
        self.address: Optional[str] = None
        self.process: Optional[asyncio.subprocess.Process] = None
        self._drain_task: Optional[asyncio.Task] = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def ensure_running(self) -> str:
        """Starts the proxy if needed and returns its base address (``http://127.0.0.1:<port>``)."""
        if self.running and self.address:
            return self.address
        await self.stop()
        args = ["proxy", "--idle-timeout", str(PROXY_IDLE_TIMEOUT_SECONDS)]
        if self.port:
            args += ["--port", str(self.port)]  # otherwise the first free port from 8787
        cmd = self.build_cmd(args)
        self.process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=self.env
        )
        output: List[str] = []
        try:
            while True:
                raw = await asyncio.wait_for(self.process.stdout.readline(), timeout=PROXY_START_TIMEOUT_SECONDS)
                if not raw:
                    raise BeeProxyError(f"bee proxy exited: {' | '.join(output)[-300:]}")
                line = raw.decode("utf-8", "replace").strip()
                output.append(line)
                match = _PROXY_ADDRESS_RE.search(line)
                if match:
                    self.address = match.group(1).rstrip("/")
                    break
        except asyncio.TimeoutError:
            await self.stop()
            raise BeeProxyError("bee proxy did not start in time")
        except BeeProxyError:
            await self.stop()
            raise
        self._drain_task = asyncio.create_task(self._drain())
        self.debug(f"Private bee proxy listening on {self.address}")
        return self.address

    async def _drain(self) -> None:
        """Keeps the proxy stdout pipe empty (it only logs errors after start-up)."""
        assert self.process is not None
        while True:
            raw = await self.process.stdout.readline()
            if not raw:
                return
            self.debug(f"bee proxy: {raw.decode('utf-8', 'replace').strip()}")

    async def stop(self) -> None:
        if self._drain_task is not None:
            self._drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._drain_task
            self._drain_task = None
        if self.running:
            self.process.terminate()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.process.wait(), timeout=5)
        self.process = None
        self.address = None


class BeeClient(Debug):
    def __init__(self, cli_path='resources/bee-cli/bin/bee.js', debug_mode="none", transport: Optional[str] = None):
        super().__init__(debug_mode=debug_mode, sector_name="BEE")
        self.cli_path = cli_path
        self.process = None
        self.transport = (transport or settings.bee_stream_transport or "proxy").strip().lower()
        self.active_transport: Optional[str] = None
        # Per-user bee-cli login (BEE_CONFIG_DIR + file store); None = the host's default login
        self.env: Optional[Dict[str, str]] = bee_subprocess_env()
        self.proxy = BeeProxy(self._build_cmd, debug_mode=debug_mode, env=self.env)
        # Seams for tests: httpx transport used to reach the private proxy, reconnect back-off sleep
        self.http_transport_factory: Callable[[str], Any] = default_http_transport
        self._sleep: Callable[[float], Any] = asyncio.sleep

    def _build_cmd(self, subcmd_args: List[str]) -> List[str]:
        bin_path = get_bee_binary_path() or self.cli_path
        if bin_path.endswith(".js"):
            runner = "bun" if shutil.which("bun") else ("node" if shutil.which("node") else "bun")
            return [runner, "run", bin_path] + subcmd_args
        return [bin_path] + subcmd_args

    async def run_json(self, subcmd_args: List[str], timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """Runs `bee <args> --json` and returns the parsed body, or None on any failure."""
        cmd = self._build_cmd(list(subcmd_args) + ["--json"])
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=self.env
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            with contextlib.suppress(Exception):
                process.kill()
            self.warn(f"bee {subcmd_args[0] if subcmd_args else ''} timed out", "bee.command_failed",
                      command=subcmd_args[0] if subcmd_args else None)
            return None
        except OSError as e:
            self.warn(f"bee {subcmd_args[0] if subcmd_args else ''} could not start: {e}", "bee.command_failed",
                      command=subcmd_args[0] if subcmd_args else None)
            return None
        if process.returncode != 0:
            self.warn(f"bee {subcmd_args[0] if subcmd_args else ''} failed (exit {process.returncode}): "
                      f"{stderr.decode('utf-8', 'replace').strip()[:300]}", "bee.command_failed",
                      command=subcmd_args[0] if subcmd_args else None)
            return None
        try:
            data = json.loads(stdout.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.debug(f"bee {' '.join(subcmd_args)} returned invalid JSON")
            return None
        return data if isinstance(data, dict) else None

    async def get_location(self) -> Optional[Dict[str, Any]]:
        """Last known Bee location (`bee locations current --json`), or None.

        Returns ``{id, latitude, longitude, address, created_at, is_recent, age_ms}``. The fix can be
        old (the Apple Watch samples it only when a conversation starts): callers must check ``is_recent``.
        """
        data = await self.run_json(["locations", "current"])
        loc = (data or {}).get("location")
        if not isinstance(loc, dict) or loc.get("latitude") is None or loc.get("longitude") is None:
            return None
        try:
            latitude, longitude = float(loc["latitude"]), float(loc["longitude"])
        except (TypeError, ValueError):
            return None
        return {
            "id": loc.get("id"),
            "latitude": latitude,
            "longitude": longitude,
            "address": loc.get("address"),
            "created_at": loc.get("created_at"),
            "is_recent": bool(data.get("is_recent")),
            "age_ms": data.get("age_ms"),
        }

    # ------------------------------------------------------------------
    # Stream transports: both yield (kind, payload_dict | None, received_at)
    # ------------------------------------------------------------------

    async def _proxy_items(self) -> AsyncIterator[Tuple[str, Optional[Dict[str, Any]], str]]:
        import httpx

        base_url = await self.proxy.ensure_running()
        queue: asyncio.Queue = asyncio.Queue()

        async def reader() -> None:
            # Lines are queued so the consumer can time out on queue.get(): wrapping the httpx line
            # iterator itself in wait_for would cancel it and close the stream.
            try:
                transport = self.http_transport_factory(base_url)
                async with httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(15.0, read=None)) as client:
                    async with client.stream("GET", f"{base_url}/v1/stream",
                                             headers={"Accept": "text/event-stream"}) as response:
                        if response.status_code != 200:
                            body = (await response.aread()).decode("utf-8", "replace")[:200]
                            raise BeeProxyError(f"stream HTTP {response.status_code}: {body}")
                        async for line in response.aiter_lines():
                            await queue.put(("line", line))
                await queue.put(("eof", None))
            except asyncio.CancelledError:
                raise
            except Exception as e:  # surfaced to the consumer
                await queue.put(("error", e))

        task = asyncio.create_task(reader())
        parser = SseFrameParser()
        timeout = settings.bee_stream_ping_timeout_seconds
        try:
            while True:
                try:
                    kind, value = await asyncio.wait_for(queue.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    raise BeeStreamTimeout(f"no SSE frame for {timeout:g}s")
                if kind == "eof":
                    return
                if kind == "error":
                    raise value
                received_at = datetime.now().isoformat()
                frame = parser.feed(value)
                if frame is None:
                    continue
                if frame[0] == "ping":
                    yield ("ping", None, received_at)
                    continue
                _, name, raw = frame
                try:
                    data = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    yield ("alive", None, received_at)
                    continue
                if not isinstance(data, dict):
                    yield ("alive", None, received_at)
                    continue
                if name and not (data.get("type") or data.get("event")):
                    data = {**data, "type": name}  # e.g. `connected` carries no type in its data
                yield ("payload", data, received_at)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _cli_items(self) -> AsyncIterator[Tuple[str, Optional[Dict[str, Any]], str]]:
        cmd = self._build_cmd(['stream', '--json'])
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            limit=1024 * 1024 * 10,
            env=self.env,
        )
        # `bee stream --json` prints nothing during silence (pings are dropped): while the process is
        # running the connection is assumed alive, and a synthetic tick keeps coverage moving.
        tick = max(1.0, settings.coverage_flush_seconds)
        while True:
            try:
                line_bytes = await asyncio.wait_for(self.process.stdout.readline(), timeout=tick)
            except asyncio.TimeoutError:
                if self.process.returncode is None:
                    yield ("alive", None, datetime.now().isoformat())
                    continue
                return
            if not line_bytes:
                return
            received_at = datetime.now().isoformat()
            line = line_bytes.decode('utf-8', 'replace').strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                # stderr is merged into stdout: non-JSON lines may be CLI errors, not liveness
                continue
            if isinstance(data, dict):
                yield ("payload", data, received_at)

    async def stream_events(self):
        """Connects to the Bee stream and yields parsed events (see ``parse_bee_payload``).

        Also yields synthetic lifecycle events used by the coverage tracker (historical backfill):
        ``stream-ping`` (server ping, proxy transport), ``stream-alive`` (any other proof of life) and
        ``stream-disconnected`` before each reconnect.
        """
        retry_delay = 1
        proxy_failures = 0
        fallback_since: Optional[float] = None

        while True:
            if fallback_since is not None and time.time() - fallback_since >= PROXY_RETRY_AFTER_SECONDS:
                proxy_failures, fallback_since = 0, None  # give the proxy another chance
            use_proxy = self.transport == "proxy" and proxy_failures < PROXY_MAX_FAILURES
            self.active_transport = "proxy" if use_proxy else "cli"
            disconnect_reason = "spawn_failed"
            try:
                items = self._proxy_items() if use_proxy else self._cli_items()
                connected = False
                async for kind, data, received_at in items:
                    if not connected:
                        connected = True
                        retry_delay = 1
                        proxy_failures = 0 if use_proxy else proxy_failures
                        disconnect_reason = "unknown"
                        self.debug(f"Connected to Bee stream ({self.active_transport}).")
                    if kind == "ping":
                        yield {"event": "stream-ping", "data": {"received_at": received_at}}
                    elif kind == "alive":
                        yield {"event": "stream-alive", "data": {}}
                    else:
                        self.debug(f"Received data: {data}", log=False)
                        yield parse_bee_payload(data, received_at)
                disconnect_reason = "eof"
            except asyncio.CancelledError:
                await self.aclose()
                raise
            except BeeStreamTimeout as e:
                self.warn(f"Stream stalled: {e}", "bee.stream_stalled", transport=self.active_transport)
                disconnect_reason = "timeout"
            except BeeProxyError as e:
                proxy_failures += 1
                self.warn(f"Proxy error ({proxy_failures}/{PROXY_MAX_FAILURES}): {e}", "bee.stream_disconnected",
                          transport="proxy", attempt=proxy_failures)
                disconnect_reason = f"proxy_error: {e}"
                await self.proxy.stop()
            except Exception as e:
                if use_proxy:
                    proxy_failures += 1
                self.warn(f"Connection error: {type(e).__name__}: {e}", "bee.stream_disconnected",
                          transport=self.active_transport, error=e)
                disconnect_reason = f"error: {e}"
            if use_proxy and proxy_failures >= PROXY_MAX_FAILURES and fallback_since is None:
                fallback_since = time.time()
                self.warn(f"Falling back to `bee stream --json` for {PROXY_RETRY_AFTER_SECONDS:g}s",
                          "bee.proxy_fallback_cli", attempt=proxy_failures)

            await self._reap_cli_process()
            yield {"event": "stream-disconnected", "data": {"reason": disconnect_reason}}
            self.debug(f"Retrying connection in {retry_delay} seconds...")
            await self._sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)

    async def stream_utterances(self):
        """Spawns the stream, yields raw utterance text strings for backward compatibility."""
        async for event in self.stream_events():
            if event.get("event") == "new-utterance":
                text = event.get("data", {}).get("text", "")
                if text:
                    self.debug(f"Extracted text: '{text}'", log=False)
                    yield text

    def _stop_cli_process(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            self.debug("Subprocess terminated.")

    async def _reap_cli_process(self) -> None:
        self._stop_cli_process()
        if self.process is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.process.wait(), timeout=5)
            self.process = None

    async def aclose(self) -> None:
        """Stops the stream subprocess and the private proxy."""
        await self._reap_cli_process()
        await self.proxy.stop()

    def stop(self):
        """Cleanly terminates the underlying subprocesses (stream and private proxy)."""
        self._stop_cli_process()
        proxy_process = self.proxy.process
        if proxy_process is not None and proxy_process.returncode is None:
            proxy_process.terminate()

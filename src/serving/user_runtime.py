"""Per-user live runtime and SSE fan-out (docs/next_steps/multi_user/03 §3, 04 §2).

``UserRuntime`` owns everything live for one user: the Bee client bound to the user's
``BEE_CONFIG_DIR``, the stream orchestrator, the Event Engine runtime, the backfill service and the
wearer identity. Everything runs inside ``acting_as(system_context(user_id))``, so tasks, timers and
worker threads started here resolve that user's scoped store. ``UserRuntimeManager`` replaces the old
single ``OrchestratorManager``.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from src.core.config import settings
from src.core.identity import acting_as, require_user, system_context
from src.core.storage import get_storage_store, get_store_registry
from src.ingestion.backfill import drop_backfill_service, get_backfill_service
from src.ingestion.bee_history import CliBeeHistorySource
from src.ingestion.bee_identity import forget_wearer_identity, get_wearer_identity
from src.ingestion.event_engine import drop_event_engine, get_event_engine_runtime
from src.ingestion.stream_convo import BeeClient

logger = logging.getLogger("examen.serving.runtime")

RESTART_BACKOFF_SECONDS = (5, 15, 60, 300)
START_STAGGER_SECONDS = 2.0


class TooManyActiveUsers(RuntimeError):
    pass


class UserEventHub:
    """SSE subscribers per user: an event published for one user reaches only that user's tabs."""

    def __init__(self):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}

    def subscribe(self, user_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.setdefault(user_id, set()).add(queue)
        return queue

    def unsubscribe(self, user_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(user_id)
        if subs is not None:
            subs.discard(queue)
            if not subs:
                self._subscribers.pop(user_id, None)

    def publish(self, user_id: str, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        payload = json.dumps({"type": event_type, "data": data or {}, "timestamp": datetime.now().isoformat()},
                             default=str)
        msg = f"data: {payload}\n\n"
        for queue in list(self._subscribers.get(user_id, ())):
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:
                self.unsubscribe(user_id, queue)

    def subscriber_count(self, user_id: str) -> int:
        return len(self._subscribers.get(user_id, ()))


_hub = UserEventHub()


def get_event_hub() -> UserEventHub:
    return _hub


class UserRuntime:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.ctx = system_context(user_id)
        registry = get_store_registry()
        self.store = get_storage_store(user_id=user_id)
        self.bee_config_dir = str(registry.bee_config_dir(user_id))
        with acting_as(self.ctx):
            self.identity = get_wearer_identity(user_id)
            self.engine_runtime = get_event_engine_runtime(user_id)
            self.backfill = get_backfill_service(user_id)
        self.engine = self.engine_runtime.engine
        if self.backfill.source_factory is CliBeeHistorySource:  # default: this user's Bee account
            self.backfill.source_factory = lambda: CliBeeHistorySource(client=self.new_bee_client())
        self.engine_runtime.add_listener(lambda event_type, payload: self.publish(event_type, payload))
        self.orchestrator = None
        self.task: Optional[asyncio.Task] = None
        self._prepared = False
        self._failures: List[float] = []

    # ------------------------------------------------------------------ wiring

    def new_bee_client(self) -> BeeClient:
        return BeeClient(config_dir=self.bee_config_dir)

    def publish(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        get_event_hub().publish(self.user_id, event_type, data)

    def ensure_engine(self):
        """Starts the Event Engine and the backfill service (needs a running loop); returns the engine."""
        with acting_as(self.ctx):
            if not self._prepared and settings.backfill_enabled:
                self._prepared = True
                self.backfill.broadcast = self.publish
                self.backfill.live_engine_getter = lambda: self.engine
                self.backfill.live_since_getter = self.live_since
                self.backfill.live_busy = self.live_busy
                try:
                    run = self.backfill.prepare_startup(self.engine if settings.event_engine_enabled else None)
                    if run is not None:
                        logger.info(f"[{self.user_id}] startup catch-up queued {run.window_from} → {run.window_to}")
                except Exception as e:
                    logger.warning(f"[{self.user_id}] backfill startup preparation failed: {e}")
            if settings.event_engine_enabled:
                self.engine_runtime.ensure_started()
            if settings.backfill_enabled:
                self.backfill.ensure_started()
        return self.engine

    # ------------------------------------------------------------------ stream

    @property
    def streaming(self) -> bool:
        return self.task is not None and not self.task.done()

    def start_stream(self) -> None:
        if self.streaming:
            return
        from src.ingestion.orchestrator import BeeStreamOrchestrator

        self.ensure_engine()
        with acting_as(self.ctx):
            self.orchestrator = BeeStreamOrchestrator(
                store=self.store, engine=self.engine, identity=self.identity, bee_factory=self.new_bee_client,
            )
            self.orchestrator.on_coverage_gap = lambda gap: self.publish("coverage_gap_detected", gap.model_dump())
            self.orchestrator.on_coverage_open = self.backfill.on_live_coverage_open
            self.task = asyncio.get_running_loop().create_task(self._run_stream())
        logger.info(f"[{self.user_id}] live ingestion started")

    async def _run_stream(self) -> None:
        while True:
            try:
                await self.orchestrator.run()
                return  # cancelled or stopped
            except asyncio.CancelledError:
                raise
            except Exception as e:
                now = time.time()
                self._failures = [t for t in self._failures if now - t < 3600] + [now]
                delay = RESTART_BACKOFF_SECONDS[min(len(self._failures) - 1, len(RESTART_BACKOFF_SECONDS) - 1)]
                logger.warning(f"[{self.user_id}] ingestion crashed ({e}); restarting in {delay}s")
                if len(self._failures) >= 5:
                    link = get_store_registry().system().get_bee_link(self.user_id)
                    link.last_error = f"Live ingestion keeps failing: {e}"[:300]
                    get_store_registry().system().save_bee_link(link)
                await asyncio.sleep(delay)

    async def stop_stream(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.task = None

    async def shutdown(self) -> None:
        await self.stop_stream()
        self.engine_runtime.stop()
        self.backfill.stop()

    # ------------------------------------------------------------------ status

    def live_since(self) -> Optional[str]:
        orch = self.orchestrator
        if orch is None or orch.coverage.current is None:
            return None
        return orch.coverage.current.start

    def live_busy(self) -> bool:
        return bool(self.orchestrator is not None and getattr(self.orchestrator, "inflight_dispatches", 0) > 0)

    def get_status(self) -> Dict[str, Any]:
        if self.orchestrator is not None and self.streaming:
            status = self.orchestrator.get_status_dict()
            status["service_managed"] = True
            return status
        return {
            "running": False,
            "status": "STOPPED",
            "mode": "ambient_sse",
            "chunks_screened": 0,
            "utterances_received": 0,
            "detail": "Live ingestion is not running (link a Bee account to start it)",
            "service_managed": True,
            "coverage": {"live_since": None, "connected": False},
        }


class UserRuntimeManager:
    def __init__(self):
        self._runtimes: Dict[str, UserRuntime] = {}

    def runtime(self, user_id: str) -> UserRuntime:
        runtime = self._runtimes.get(user_id)
        if runtime is None:
            runtime = UserRuntime(user_id)
            self._runtimes[user_id] = runtime
        return runtime

    def current(self) -> UserRuntime:
        return self.runtime(require_user().user_id)

    def get(self, user_id: str) -> Optional[UserRuntime]:
        return self._runtimes.get(user_id)

    def active_streams(self) -> int:
        return sum(1 for r in self._runtimes.values() if r.streaming)

    def start_stream(self, user_id: str) -> UserRuntime:
        runtime = self.runtime(user_id)
        if not runtime.streaming and self.active_streams() >= settings.max_active_users:
            raise TooManyActiveUsers(f"MAX_ACTIVE_USERS={settings.max_active_users} live streams already running")
        runtime.start_stream()
        return runtime

    async def start_all_linked(self) -> int:
        started = 0
        for link in get_store_registry().system().list_bee_links(state="linked"):
            try:
                self.start_stream(link.user_id)
                started += 1
            except TooManyActiveUsers as e:
                logger.warning(f"Not starting {link.user_id}: {e}")
                break
            except Exception as e:
                logger.warning(f"Failed to start live ingestion for {link.user_id}: {e}")
            await asyncio.sleep(START_STAGGER_SECONDS)
        return started

    async def stop_stream(self, user_id: str) -> None:
        runtime = self._runtimes.get(user_id)
        if runtime is not None:
            await runtime.stop_stream()

    async def drop(self, user_id: str) -> None:
        """Stops and forgets everything live for a user (unlink with data erasure, account deletion)."""
        runtime = self._runtimes.pop(user_id, None)
        if runtime is not None:
            await runtime.shutdown()
        drop_event_engine(user_id)
        drop_backfill_service(user_id)
        forget_wearer_identity(user_id)

    async def shutdown_all(self) -> None:
        for runtime in list(self._runtimes.values()):
            await runtime.shutdown()


_manager: Optional[UserRuntimeManager] = None


def get_runtime_manager() -> UserRuntimeManager:
    global _manager
    if _manager is None:
        _manager = UserRuntimeManager()
    return _manager


def reset_runtime_manager(manager: Optional[UserRuntimeManager] = None) -> None:
    global _manager
    _manager = manager

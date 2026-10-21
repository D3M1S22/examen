"""Health monitor: anomaly rules → incidents (docs/next_steps/admin_console/03 §5).

One asyncio task: samples LLM slot occupancy every 10 s, re-reads runtime settings every 30 s
(other processes), and every ``HEALTH_CHECK_INTERVAL_SECONDS`` evaluates the rules below. A failing
rule opens (or updates) the incident ``check:<rule>[:<user_id>]``; a passing rule resolves it.
Rates come from the in-memory counters of ``src/core/metrics.py``; nothing here reads user data.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.core import token_usage
from src.core.config import settings
from src.core.limits import llm_slots_in_use
from src.core.metrics import Metrics, metrics as default_metrics, percentile
from src.core.ops_store import get_ops_store, iso
from src.core.service_log import get_sink, resolve_incident, resolve_quiet_incidents, upsert_incident
from src.core.tenancy import data_root

logger = logging.getLogger("examen.health")

AI_CHECKS = {"check.gatekeeper_degraded", "check.pipeline_errors", "check.llm_latency"}
AI_EVENT_CODES = {"llm.invalid_model", "llm.access_denied", "llm.throttled"}


def read_memory() -> Tuple[Optional[int], Optional[int]]:
    """(process RSS, memory limit) in bytes: cgroup v2 / v1 limit, else the host's MemTotal."""
    rss = limit = None
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1]) * 1024
    except OSError:
        pass
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            raw = open(path).read().strip()
            if raw.isdigit() and int(raw) < 1 << 60:
                limit = int(raw)
                break
        except OSError:
            continue
    if limit is None:
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        limit = int(line.split()[1]) * 1024
        except OSError:
            pass
    return rss, limit


def read_disk(path: Optional[str] = None) -> Tuple[Optional[int], Optional[int]]:
    try:
        usage = shutil.disk_usage(path or str(data_root()))
        return usage.free, usage.total
    except OSError:
        return None, None


class HealthMonitor:
    def __init__(self, *, stream_snapshot: Callable[[], List[Dict[str, Any]]] = lambda: [],
                 store_getter: Callable = get_ops_store, metrics: Metrics = default_metrics,
                 clock: Callable[[], float] = time.time,
                 memory_reader: Callable[[], Tuple[Optional[int], Optional[int]]] = read_memory,
                 disk_reader: Callable[[], Tuple[Optional[int], Optional[int]]] = read_disk,
                 settings_service: Any = None, on_incident: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.stream_snapshot = stream_snapshot
        self.store_getter = store_getter
        self.metrics = metrics
        self.clock = clock
        self.memory_reader = memory_reader
        self.disk_reader = disk_reader
        self.settings_service = settings_service
        self.on_incident = on_incident
        self.started_at = clock()
        self._first_seen: Dict[str, float] = {}
        self._backfill_failures: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._last_purge = 0.0
        self._task: Optional[asyncio.Task] = None
        self._sink = None

    # -- inputs -----------------------------------------------------------------

    def _on_sink(self, kind: str, payload: Dict[str, Any]) -> None:
        if kind != "event" or not payload.get("user_id"):
            return
        uid = payload["user_id"]
        with self._lock:
            if payload["code"] == "backfill.run_failed":
                self._backfill_failures[uid] = self._backfill_failures.get(uid, 0) + 1
            elif payload["code"] == "backfill.run_completed":
                self._backfill_failures.pop(uid, None)

    def sample(self) -> None:
        capacity = max(1, int(settings.max_concurrent_llm_calls))
        self.metrics.observe("llm.slots_saturated", 1.0 if llm_slots_in_use() >= capacity else 0.0)

    # -- rules --------------------------------------------------------------------

    def _rule(self, rule: str, failing: bool, *, component: str, severity: str, title: str,
              user_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        store = self.store_getter()
        fp = f"check:{rule}:{user_id or ''}"
        now = iso(datetime.fromtimestamp(self.clock(), timezone.utc))
        if failing:
            change_id = None
            if rule in AI_CHECKS and self.settings_service is not None:
                change_id = self.settings_service.recent_ai_change()
            return upsert_incident(store, fp, code=rule, component=component, severity=severity, title=title,
                                   user_id=user_id, at=now, details=details, change_id=change_id)
        return resolve_incident(store, fp, at=now)

    def tick(self) -> List[Dict[str, Any]]:
        """Evaluates every rule once; returns the incidents opened, updated or resolved."""
        changed: List[Optional[Dict[str, Any]]] = []
        now = self.clock()
        m = self.metrics
        token_usage.flush(self.store_getter)  # hourly token totals → ops.db (03 §8)

        # Per-user Bee streams
        seen = set()
        for info in self.stream_snapshot():
            uid = info["user_id"]
            seen.add(uid)
            if not info.get("linked"):
                changed.append(self._rule("check.stream_silent", False, component="bee", severity="warning",
                                          title="", user_id=uid))
                continue
            last = info.get("last_frame") or self._first_seen.setdefault(uid, now)
            silent_for = now - last
            silent = (not info.get("capacity_since")) and silent_for >= settings.health_stream_silent_minutes * 60
            changed.append(self._rule(
                "check.stream_silent", silent, component="bee", severity="warning", user_id=uid,
                title=f"Bee stream silent for {int(silent_for // 60)} min", details={"transport": info.get("transport")}))
            flaps = m.count("event:bee.stream_disconnected", 1800, uid)
            changed.append(self._rule(
                "check.stream_flapping", flaps >= settings.health_stream_flaps_per_30min, component="bee",
                severity="warning", user_id=uid, title=f"Bee stream reconnected {int(flaps)} times in 30 min"))
            since = info.get("capacity_since")
            waiting = bool(since) and now - since >= settings.health_capacity_minutes * 60
            changed.append(self._rule(
                "check.capacity", waiting, component="orchestrator", severity="warning", user_id=uid,
                title=f"Waiting for a live stream slot (MAX_ACTIVE_USERS={settings.max_active_users})"))
        for uid in list(self._first_seen):
            if uid not in seen:
                self._first_seen.pop(uid, None)

        # Model quality and provider health
        calls = m.count("gatekeeper.calls", 900)
        fallbacks = m.count("event:gatekeeper.fallback", 900)
        rate = fallbacks / calls if calls else 0.0
        changed.append(self._rule(
            "check.gatekeeper_degraded", calls >= 10 and rate >= settings.health_fallback_rate,
            component="gatekeeper", severity="error",
            title=f"Gatekeeper falling back to heuristics on {rate:.0%} of calls (15 min)",
            details={"calls": int(calls), "fallbacks": int(fallbacks)}))
        dispatches = m.count("pipeline.dispatches", 900)
        errors = m.count("event:pipeline.dispatch_failed", 900) + m.count("event:pipeline.node_fallback", 900)
        changed.append(self._rule(
            "check.pipeline_errors",
            dispatches >= 5 and errors / dispatches >= settings.health_pipeline_error_rate,
            component="pipeline", severity="error",
            title=f"Pipeline errors or fallbacks on {errors / dispatches if dispatches else 0:.0%} of dispatches",
            details={"dispatches": int(dispatches), "errors": int(errors)}))
        throttled = m.count("event:llm.throttled", 300)
        changed.append(self._rule(
            "check.llm_throttling", throttled >= settings.health_throttle_per_5min, component="llm",
            severity="warning", title=f"Model provider throttling: {int(throttled)} events in 5 min"))
        latencies = m.values("gatekeeper.latency_ms", 900)
        p95 = percentile(latencies, 0.95)
        changed.append(self._rule(
            "check.llm_latency", len(latencies) >= 10 and p95 is not None and p95 > settings.health_gatekeeper_p95_ms,
            component="llm", severity="warning", title=f"Gatekeeper p95 latency {int(p95 or 0)} ms (15 min)"))
        saturated = m.values("llm.slots_saturated", 600)
        share = sum(saturated) / len(saturated) if saturated else 0.0
        changed.append(self._rule(
            "check.llm_slots_saturated", len(saturated) >= 10 and share >= settings.health_llm_saturation,
            component="llm", severity="warning",
            title=f"All {settings.max_concurrent_llm_calls} LLM slots busy {share:.0%} of the time (10 min)"))

        # Backfill
        with self._lock:
            failures = dict(self._backfill_failures)
        for uid, count in failures.items():
            changed.append(self._rule("check.backfill_failing", count >= 2, component="backfill", severity="warning",
                                      user_id=uid, title=f"{count} consecutive history backfill runs failed"))
        for inc in self.store_getter().list_incidents(status="active", component="backfill", limit=100):
            if inc["code"] == "check.backfill_failing" and inc.get("user_id") not in failures:
                changed.append(self._rule("check.backfill_failing", False, component="backfill", severity="warning",
                                          title="", user_id=inc.get("user_id")))

        # Host
        free, total = self.disk_reader()
        low_disk = free is not None and total and (free < settings.health_min_disk_gb * 1024 ** 3 or free / total < 0.10)
        changed.append(self._rule("check.disk_space", bool(low_disk), component="system", severity="critical",
                                  title=f"Low disk space: {(free or 0) / 1024 ** 3:.1f} GB free in the data directory"))
        rss, limit = self.memory_reader()
        high_mem = bool(rss and limit and rss / limit > settings.health_memory_fraction)
        changed.append(self._rule("check.memory", high_mem, component="system", severity="warning",
                                  title=f"Memory: {(rss or 0) / 1024 ** 2:.0f} MB of {(limit or 0) / 1024 ** 2:.0f} MB"))
        errors_5m = m.count("level:error", 300) + m.count("level:critical", 300)
        changed.append(self._rule("check.error_burst", errors_5m >= settings.health_error_burst_per_5min,
                                  component="system", severity="error", title=f"{int(errors_5m)} errors in 5 min"))

        # Provider errors right after a model settings change get the change id (revert button)
        if self.settings_service is not None:
            change_id = self.settings_service.recent_ai_change()
            if change_id:
                store = self.store_getter()
                for inc in store.list_incidents(status="active", component="llm", limit=50):
                    if inc["code"] in AI_EVENT_CODES and not inc.get("change_id"):
                        inc["change_id"] = change_id
                        changed.append(store.save_incident(inc))

        # Housekeeping: quiet event incidents, daily retention
        store = self.store_getter()
        changed.extend(resolve_quiet_incidents(store, now=datetime.fromtimestamp(now, timezone.utc)))
        if now - self._last_purge >= 86400:
            self._last_purge = now
            store.purge(event_days=settings.service_log_retention_days, max_events=settings.service_log_max_events,
                        usage_days=settings.token_usage_retention_days)
            store.vacuum_if_fragmented()

        out = [c for c in changed if c]
        if self.on_incident:
            for inc in out:
                try:
                    self.on_incident(inc)
                except Exception:  # pragma: no cover - defensive
                    pass
        return out

    # -- snapshot (GET /api/admin/health) ---------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        m = self.metrics
        calls = m.count("gatekeeper.calls", 900)
        fallbacks = m.count("event:gatekeeper.fallback", 900)
        dispatches = m.count("pipeline.dispatches", 900)
        latencies = m.values("gatekeeper.latency_ms", 900)
        free, total = self.disk_reader()
        rss, limit = self.memory_reader()
        now = self.clock()
        streams = []
        for info in self.stream_snapshot():
            last = info.get("last_frame")
            streams.append({
                "user_id": info["user_id"], "linked": bool(info.get("linked")), "streaming": bool(info.get("running")),
                "transport": info.get("transport"), "last_frame_age_s": round(now - last) if last else None,
                "capacity_wait_s": round(now - info["capacity_since"]) if info.get("capacity_since") else None,
                "link_state": info.get("link_state"),
            })
        incidents = self.store_getter().list_incidents(status="active", limit=500)
        by_severity: Dict[str, int] = {}
        for inc in incidents:
            by_severity[inc["severity"]] = by_severity.get(inc["severity"], 0) + 1
        return {
            "uptime_s": round(now - self.started_at),
            "pid": os.getpid(),
            "memory": {"rss_bytes": rss, "limit_bytes": limit},
            "disk": {"free_bytes": free, "total_bytes": total},
            "streams": {"active": sum(1 for s in streams if s["streaming"]), "max": settings.max_active_users,
                        "users": streams},
            "llm": {"slots_in_use": llm_slots_in_use(), "slots_max": settings.max_concurrent_llm_calls,
                    "gatekeeper_calls_15m": int(calls), "gatekeeper_fallbacks_15m": int(fallbacks),
                    "gatekeeper_fallback_rate": round(fallbacks / calls, 3) if calls else None,
                    "gatekeeper_p95_ms": round(percentile(latencies, 0.95) or 0) if latencies else None,
                    "pipeline_dispatches_15m": int(dispatches)},
            "errors_15m": int(m.count("level:error", 900) + m.count("level:critical", 900)),
            "warnings_15m": int(m.count("level:warning", 900)),
            "incidents_open": by_severity,
            "service_log_dropped": get_sink().dropped,
            "tokens_24h": self._tokens_24h(),
        }

    def _tokens_24h(self) -> Dict[str, Any]:
        """Light token summary for the health cards (the full breakdown is /api/admin/usage)."""
        token_usage.flush(self.store_getter)
        since = datetime.fromtimestamp(self.clock() - 86400, timezone.utc).replace(minute=0, second=0, microsecond=0)
        summary = self.store_getter().token_usage_summary(iso(since))
        totals = summary["totals"]
        top = summary["by_model"][0] if summary["by_model"] else None
        return {
            "calls": totals["calls"],
            "tokens": totals["input_tokens"] + totals["output_tokens"],
            "top_model": top["model_id"] if top else None,
            "top_model_tokens": (top["input_tokens"] + top["output_tokens"]) if top else 0,
        }

    # -- loop -------------------------------------------------------------------------

    async def run(self) -> None:
        last_check = last_sync = 0.0
        while True:
            try:
                self.sample()
                now = self.clock()
                if self.settings_service is not None and now - last_sync >= 30:
                    last_sync = now
                    await self.settings_service.sync()
                if now - last_check >= settings.health_check_interval_seconds:
                    last_check = now
                    await asyncio.to_thread(self.tick)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Health monitor iteration failed: {type(e).__name__}: {e}", exc_info=True)
            await asyncio.sleep(10)

    def attach(self) -> None:
        """Listens to the service log (backfill run outcomes)."""
        if self._sink is None:
            self._sink = get_sink()
            self._sink.add_listener(self._on_sink)

    def start(self) -> asyncio.Task:
        self.attach()
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self.run())
        return self._task

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        if self._sink is not None:
            self._sink.remove_listener(self._on_sink)
            self._sink = None

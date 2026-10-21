"""Service log: structured, sanitised events and incidents for the admin console.

docs/next_steps/admin_console/03. Three capture paths feed one sink:

- ``report_event(code, …)``: explicit events from the event code catalogue (§4.5);
- ``ServiceLogHandler``: every ``WARNING``+ record of the ``examen`` loggers (``extra={"event_code": …,
  "ctx": {…}}`` sets a catalogue code without changing the message);
- unhandled errors: ASGI middleware, asyncio / thread hooks, ``watch_task`` done-callbacks.

The admin manages the service and never reads users' data: messages are sanitised (quoted text,
e-mails, IPs, keys, long exception tails), only whitelisted context keys are kept, and tracebacks are
reduced to the error type and the innermost ``src/`` location. The full text stays in journald.

Writes never block: events go to a bounded queue, a writer thread stores them in ``ops.db`` in
batches and groups them into incidents.
"""

from __future__ import annotations

import hashlib
import logging
import queue
import re
import threading
import traceback
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from src.core.metrics import metrics
from src.core.ops_store import LEVELS, get_ops_store, iso, utcnow
from src.core.tenancy import get_tenant_id

ops_logger = logging.getLogger("examen.ops")  # never captured by ServiceLogHandler (no loops)

CONTEXT_KEYS = frozenset({
    "session_id", "event_id", "run_id", "conversation_uuid", "source_key", "model_id", "provider", "region",
    "transport", "attempt", "latency_ms", "status_code", "count", "threshold", "value", "change_id", "node",
    "command", "rule", "version", "commit",
})
PER_USER_COMPONENTS = frozenset({"bee", "orchestrator", "backfill"})
QUEUE_SIZE = 10_000
WARNING_INCIDENT_COUNT = 5
WARNING_INCIDENT_WINDOW = timedelta(minutes=15)
REOPEN_WINDOW = timedelta(minutes=30)
_CURRENT = object()

# ---------------------------------------------------------------------------
# Sanitising (03 §3)
# ---------------------------------------------------------------------------

_QUOTED = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"|“[^”\n]*”|‘[^’\n]*’")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){3,7}[0-9a-fA-F]{1,4}\b")
_URL_QUERY = re.compile(r"(https?://[^/\s?#]+)[^\s?#]*\?\S*")
_SECRETS = [
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "<aws-key>"),
    (re.compile(r"bedrock-api-key-[A-Za-z0-9+/=_-]+"), "<api-key>"),
    (re.compile(r"\bexm_[A-Za-z0-9_-]{8,}"), "<token>"),
    (re.compile(r"(?i)\bbearer\s+\S+"), "Bearer <redacted>"),
    (re.compile(r"(?i)\b(authorization|api[_-]?key|secret|password|token)([\"']?\s*[:=]\s*)\S+"), r"\1\2<redacted>"),
]
_TAIL_LIMIT = 120
MESSAGE_LIMIT = 300


def _quote_mask(match: "re.Match[str]") -> str:
    text = match.group(0)
    return f"{text[0]}…{text[-1]}"


def sanitize(message: Any) -> str:
    """Removes user content and secrets from a log message (03 §3.1)."""
    text = str(message or "").replace("\r", " ").replace("\n", " ").strip()
    for pattern, repl in _SECRETS:
        text = pattern.sub(repl, text)
    text = _QUOTED.sub(_quote_mask, text)
    text = _EMAIL.sub("<email>", text)
    text = _URL_QUERY.sub(r"\1/…", text)
    text = _IPV6.sub("<ip>", text)
    text = _IPV4.sub("<ip>", text)
    head, sep, tail = text.partition(": ")
    if sep and len(tail) > _TAIL_LIMIT:
        text = f"{head}: {tail[:_TAIL_LIMIT].rstrip()}…"
    if len(text) > MESSAGE_LIMIT:
        text = text[:MESSAGE_LIMIT - 1].rstrip() + "…"
    return text


def clean_context(ctx: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in (ctx or {}).items():
        if key not in CONTEXT_KEYS or value is None:
            continue
        if isinstance(value, (int, float, bool)):
            out[key] = value
        else:
            out[key] = sanitize(value)[:_TAIL_LIMIT]
    return out


def component_for(logger_name: str) -> str:
    name = logger_name or ""
    table = (
        ("examen.ingestion.orchestrator", "orchestrator"), ("examen.ingestion.gatekeeper", "gatekeeper"),
        ("examen.ingestion.stream_convo", "bee"), ("examen.ingestion.bee_", "bee"),
        ("examen.ingestion.event_engine", "event_engine"), ("examen.ingestion.topic_continuity", "event_engine"),
        ("examen.ingestion.session_manager", "event_engine"), ("examen.ingestion.backfill", "backfill"),
        ("examen.ingestion.bee_history", "backfill"), ("examen.ingestion.coverage", "backfill"),
        ("examen.pipeline", "pipeline"), ("examen.web_search", "pipeline"), ("examen.storage", "storage"),
        ("examen.auth", "auth"), ("examen.serving.auth", "auth"), ("examen.core.models", "llm"),
        ("examen.settings", "settings"), ("examen.serving", "serving"), ("examen.health", "system"),
    )
    for prefix, component in table:
        if name.startswith(prefix):
            return component
    return "system"


def _location(exc: Optional[BaseException], fallback: Optional[str] = None) -> Optional[str]:
    if exc is not None and exc.__traceback__ is not None:
        frames = [f for f in traceback.extract_tb(exc.__traceback__) if "/src/" in f.filename.replace("\\", "/")]
        if frames:
            f = frames[-1]
            path = f.filename.replace("\\", "/")
            return f"{path[path.rindex('/src/') + 1:]}:{f.lineno} {f.name}"
    return fallback


def _error_type(exc: Optional[BaseException]) -> Optional[str]:
    if exc is None:
        return None
    cls = type(exc)
    if cls.__name__ == "ClientError" and hasattr(exc, "response"):
        code = (getattr(exc, "response", {}) or {}).get("Error", {}).get("Code")
        if code:
            return f"botocore.{code}"
    module = cls.__module__
    return cls.__name__ if module in ("builtins", "__main__") else f"{module}.{cls.__name__}"


def fingerprint(code: str, component: str, error_type: Optional[str], location: Optional[str],
                user_id: Optional[str] = None) -> str:
    raw = "|".join([code, component, error_type or "", location or "", user_id or ""])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Sink
# ---------------------------------------------------------------------------

Listener = Callable[[str, Dict[str, Any]], None]


class EventSink:
    """Bounded queue → writer thread → ops.db; groups events into incidents and notifies listeners."""

    def __init__(self, store_getter: Callable = get_ops_store, clock: Callable[[], datetime] = utcnow):
        self._store_getter = store_getter
        self.clock = clock
        self._queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=QUEUE_SIZE)
        self._thread: Optional[threading.Thread] = None
        self._start_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._listeners: List[Listener] = []
        self._warning_hits: Dict[str, List[datetime]] = {}
        self.dropped = 0
        self.enabled = True
        self._pending = 0  # submitted, not yet written (flush waits for in-flight batches too)
        self._idle = threading.Condition()

    def add_listener(self, listener: Listener) -> None:
        """``listener(kind, payload)`` with kind ``event`` or ``incident``, called from the writer thread."""
        self._listeners.append(listener)

    def remove_listener(self, listener: Listener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify(self, kind: str, payload: Dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(kind, payload)
            except Exception as e:  # pragma: no cover - defensive
                ops_logger.debug(f"service log listener failed: {e}")

    def submit(self, event: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        with self._idle:
            self._pending += 1
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped += 1
            try:  # make room: drop the oldest queued event, keep the new one
                self._queue.get_nowait()
                self._queue.put_nowait(event)
            except (queue.Empty, queue.Full):
                pass
            self._done(1)
        self._ensure_thread()

    def _done(self, n: int) -> None:
        with self._idle:
            self._pending = max(0, self._pending - n)
            if self._pending == 0:
                self._idle.notify_all()

    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        with self._start_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="examen-service-log", daemon=True)
                self._thread.start()

    def _run(self) -> None:
        while True:
            try:
                first = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            batch = [first]
            while len(batch) < 500:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            self._write(batch)

    def flush(self, timeout: float = 5.0) -> None:
        """Writes everything queued now and waits for batches in flight (tests, shutdown, erasure)."""
        batch = []
        while True:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            self._write(batch)
        with self._idle:
            self._idle.wait_for(lambda: self._pending == 0, timeout=timeout)

    def _write(self, batch: List[Dict[str, Any]]) -> None:
        with self._write_lock:
            try:
                store = self._store_getter()
                store.insert_events(batch)
                if self.dropped:
                    dropped, self.dropped = self.dropped, 0
                    store.insert_events([build_event("system.events_dropped", "warning",
                                                     f"Service log queue full: {dropped} events dropped",
                                                     component="system", user_id=None, count=dropped)])
                for event in batch:
                    self._notify("event", event)
                    incident = self._observe(store, event)
                    if incident is not None:
                        self._notify("incident", incident)
            except Exception as e:
                ops_logger.debug(f"service log write failed: {e}")
            finally:
                self._done(len(batch))

    # -- incidents (03 §6) --------------------------------------------------------

    def _observe(self, store, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        level = LEVELS.get(event["level"], 0)
        if level < LEVELS["warning"]:
            return None
        if level == LEVELS["warning"]:
            at = datetime.fromisoformat(event["at"])
            hits = [t for t in self._warning_hits.get(event["fingerprint"], []) if at - t < WARNING_INCIDENT_WINDOW]
            hits.append(at)
            self._warning_hits[event["fingerprint"]] = hits[-WARNING_INCIDENT_COUNT:]
            active = store.latest_incident(event["fingerprint"])
            if len(hits) < WARNING_INCIDENT_COUNT and not (active and active["status"] != "resolved"):
                return None
        return upsert_incident(store, event["fingerprint"], code=event["code"], component=event["component"],
                               severity=event["level"], title=event["message"], user_id=event.get("user_id"),
                               at=event["at"], increment=1)


def upsert_incident(store, fp: str, *, code: str, component: str, severity: str, title: str,
                    user_id: Optional[str], at: Optional[str] = None, increment: int = 1,
                    details: Optional[Dict[str, Any]] = None, change_id: Optional[str] = None) -> Dict[str, Any]:
    """Opens, updates or re-opens the incident of a fingerprint."""
    now = at or iso(utcnow())
    latest = store.latest_incident(fp)
    worse = lambda a, b: a if LEVELS.get(a, 0) >= LEVELS.get(b, 0) else b  # noqa: E731
    if latest and latest["status"] in ("open", "acknowledged"):
        latest.update(count=latest["count"] + increment, last_seen=now, severity=worse(severity, latest["severity"]))
        if details:
            latest["details"] = details
        if change_id and not latest.get("change_id"):
            latest["change_id"] = change_id
        return store.save_incident(latest)
    if latest and latest["status"] == "resolved" and latest.get("resolved_at") and \
            datetime.fromisoformat(now) - datetime.fromisoformat(latest["resolved_at"]) < REOPEN_WINDOW:
        latest.update(status="open", resolved_at=None, ack_by=None, count=latest["count"] + increment,
                      last_seen=now, severity=severity, details=details or latest.get("details"),
                      change_id=change_id or latest.get("change_id"))
        return store.save_incident(latest)
    return store.save_incident({
        "id": f"inc_{uuid.uuid4().hex[:12]}", "fingerprint": fp, "code": code, "component": component,
        "severity": severity, "title": sanitize(title)[:160], "user_id": user_id, "status": "open",
        "count": max(increment, WARNING_INCIDENT_COUNT if severity == "warning" and not fp.startswith("check:") else 1),
        "first_seen": now, "last_seen": now, "details": details or {}, "change_id": change_id,
    })


def resolve_incident(store, fp: str, at: Optional[str] = None) -> Optional[Dict[str, Any]]:
    latest = store.latest_incident(fp)
    if latest and latest["status"] in ("open", "acknowledged"):
        latest.update(status="resolved", resolved_at=at or iso(utcnow()))
        return store.save_incident(latest)
    return None


def resolve_quiet_incidents(store, quiet: timedelta = timedelta(minutes=60),
                            now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Event incidents without a new occurrence for ``quiet`` are resolved (health checks resolve their own)."""
    now = now or utcnow()
    resolved = []
    for inc in store.list_incidents(status="active", limit=500):
        if inc["fingerprint"].startswith("check:"):
            continue
        if now - datetime.fromisoformat(inc["last_seen"]) >= quiet:
            inc.update(status="resolved", resolved_at=iso(now))
            resolved.append(store.save_incident(inc))
    return resolved


_sink = EventSink()


def get_sink() -> EventSink:
    return _sink


def reset_sink(sink: Optional[EventSink] = None) -> EventSink:
    """Test seam."""
    global _sink
    _sink = sink or EventSink()
    return _sink


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_event(code: str, level: str, message: str, *, component: str, user_id: Optional[str],
                error: Optional[BaseException] = None, location: Optional[str] = None,
                **ctx: Any) -> Dict[str, Any]:
    level = level if level in LEVELS else "warning"
    err_type = _error_type(error)
    loc = _location(error, location)
    # Per-user problems (a Bee stream, a backfill) are grouped per user; others per code location
    group_user = user_id if component in PER_USER_COMPONENTS else None
    return {
        "ref": uuid.uuid4().hex[:12],
        "at": iso(utcnow()),
        "level": level,
        "code": code,
        "component": component,
        "user_id": user_id,
        "message": sanitize(message or code),
        "fingerprint": fingerprint(code, component, err_type, loc, group_user),
        "context": clean_context(ctx),
        "error_type": err_type,
        "location": loc,
    }


def report_event(code: str, level: str = "warning", message: str = "", *, component: Optional[str] = None,
                 user_id: Any = _CURRENT, error: Optional[BaseException] = None, location: Optional[str] = None,
                 **ctx: Any) -> str:
    """Records one catalogue event; returns its reference (shown to users as an error id)."""
    uid = get_tenant_id() if user_id is _CURRENT else user_id
    comp = component or code.split(".", 1)[0]
    event = build_event(code, level, message, component=comp, user_id=uid, error=error, location=location,
                        **{k: v for k, v in ctx.items() if k in CONTEXT_KEYS})
    metrics.incr(f"event:{code}", uid)
    metrics.incr(f"level:{event['level']}")
    _sink.submit(event)
    return event["ref"]


_RECORD_LEVELS = {logging.WARNING: "warning", logging.ERROR: "error", logging.CRITICAL: "critical"}


class ServiceLogHandler(logging.Handler):
    """``WARNING``+ records of the ``examen`` loggers become service events (03 §4.1)."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("examen.ops"):
            return
        try:
            level = _RECORD_LEVELS.get(record.levelno, "critical" if record.levelno > logging.CRITICAL else "warning")
            error = record.exc_info[1] if record.exc_info else None
            code = getattr(record, "event_code", None) or f"log.{level}"
            fallback = None
            path = (record.pathname or "").replace("\\", "/")
            if "/src/" in path:
                fallback = f"{path[path.rindex('/src/') + 1:]}:{record.lineno} {record.funcName}"
            ctx = {k: v for k, v in (getattr(record, "ctx", None) or {}).items() if k in CONTEXT_KEYS}
            report_event(code, level, record.getMessage(), component=getattr(record, "component", None)
                         or component_for(record.name), error=error, location=fallback, **ctx)
        except Exception:  # pragma: no cover - never break the caller's logging
            self.handleError(record)


def report_task_failure(code: str, component: str) -> Callable[[Any], None]:
    """Done-callback for background tasks: an exception that ended the task becomes an ``error`` event."""
    uid = get_tenant_id()

    def _done(task: Any) -> None:
        try:
            if task.cancelled():
                return
            exc = task.exception()
        except Exception:
            return
        if exc is not None:
            report_event(code, "error", f"{component} task ended: {type(exc).__name__}: {exc}",
                         component=component, user_id=uid, error=exc)

    return _done


def watch_task(task: Any, code: str, component: str) -> Any:
    task.add_done_callback(report_task_failure(code, component))
    return task


# ---------------------------------------------------------------------------
# Model provider errors (llm.*)
# ---------------------------------------------------------------------------

_THROTTLED = {"ThrottlingException", "TooManyRequestsException", "RateLimitError", "ServiceQuotaExceededException"}
_DENIED = {"AccessDeniedException", "UnrecognizedClientException", "ExpiredTokenException", "AuthenticationError",
           "PermissionDeniedError", "InvalidSignatureException", "NoCredentialsError"}
_INVALID_MODEL = {"ResourceNotFoundException", "NotFoundError", "ModelNotReadyException"}


def classify_llm_error(exc: BaseException) -> Optional[str]:
    names = {type(exc).__name__}
    code = ((getattr(exc, "response", None) or {}).get("Error", {}) or {}).get("Code")
    if code:
        names.add(code)
    text = str(exc).lower()
    if names & _THROTTLED or "throttl" in text or "too many requests" in text or " 429" in text:
        return "llm.throttled"
    if names & _DENIED or "access denied" in text or "not authorized" in text or "security token" in text:
        return "llm.access_denied"
    if names & _INVALID_MODEL or (("validationexception" in text or "badrequest" in text or "invalid" in text)
                                   and "model" in text):
        return "llm.invalid_model"
    return None


def note_llm_error(exc: BaseException, *, provider: Optional[str] = None, model_id: Optional[str] = None,
                   region: Optional[str] = None) -> Optional[str]:
    """Reports throttling / denied / invalid-model failures of a model call (the caller still falls back)."""
    code = classify_llm_error(exc)
    if code is None:
        return None
    level = "warning" if code == "llm.throttled" else "error"
    report_event(code, level, f"{type(exc).__name__}: {exc}", component="llm", error=exc,
                 provider=provider, model_id=model_id, region=region)
    return code


def model_fallback(log: logging.Logger, node: str, error: BaseException, *, role: str = "fast") -> None:
    """A pipeline node's model call failed and it fell back to heuristics: one coded warning (no user
    content in the message) plus the ``llm.*`` classification of the provider error."""
    from src.core.config import settings

    if role == "reasoner":
        provider, model_id = settings.reasoner_provider, settings.reasoner_model_id
    elif role == "embeddings":
        provider, model_id = "bedrock", settings.embedding_model_id
    else:
        provider, model_id = settings.gatekeeper_provider, settings.gatekeeper_model_id
    log.warning(f"{node}: model call failed, heuristic used: {type(error).__name__}: {error}",
                extra={"event_code": "pipeline.node_fallback",
                       "ctx": {"node": node, "provider": provider, "model_id": model_id}})
    note_llm_error(error, provider=provider, model_id=model_id, region=settings.aws_region)

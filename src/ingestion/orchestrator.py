import asyncio
import logging
import statistics
import time
import argparse
import signal
from collections import OrderedDict, deque
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import sys
from pathlib import Path

# Add project root (two levels up from src/ingestion/) to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.ingestion.stream_convo import BeeClient, normalize_bee_time
from src.ingestion.bee_identity import UNTAGGED, SpeakerMatch, WearerIdentity, get_wearer_identity
from src.ingestion.coverage import (
    CoverageTracker,
    ledger_entry_for_chunk,
    live_source_key,
    stable_chunk_id,
)
from src.ingestion.debug import Debug
from src.ingestion.event_engine import (
    EventEngine,
    EventEngineRuntime,
    build_continuity_from_settings,
    get_event_engine,
)
from src.ingestion.gatekeeper import aclassify_chunk, is_noop
from src.ingestion.ring_buffer import ContextRingBuffer
from src.core.config import settings
from src.core.storage import get_storage_store
from src.core.limits import llm_slot
from src.core.metrics import metrics
from src.core.tenancy import get_tenant_id
from src.core.schemas import CoverageGap, CoverageInterval, LocationTelemetry, SpeakerAttribution, UtteranceChunk

# Bounded caches keyed by Bee utterance id (speaker tags, utterance → conversation uuid)
_ID_CACHE_SIZE = 2000


def _epoch(iso: Optional[str]) -> float:
    """Receive time of an utterance (BeeClient stamps ``received_at``); now when missing or invalid."""
    if iso:
        try:
            return datetime.fromisoformat(iso).timestamp()
        except ValueError:
            pass
    return time.time()


def _remember(cache: "OrderedDict[str, Any]", key: str, value: Any) -> None:
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > _ID_CACHE_SIZE:
        cache.popitem(last=False)


class BeeStreamOrchestrator(Debug):
    """Consumes the Bee event stream: screens each utterance, feeds the Deep Topic Event Engine
    and dispatches qualified chunks to the LangGraph pipeline.

    Payload semantics follow the observed Bee contract (docs/10_bee_cli_reference.md): speaker identity
    comes from `tagged-utterance`, locations from `bee locations current` polling (the Apple Watch emits
    no `update-location`), liveness from SSE pings.
    """

    def __init__(
        self,
        debug_mode="none",
        ring_buffer_capacity=4,
        store=None,
        engine: Optional[EventEngine] = None,
        identity: Optional[WearerIdentity] = None,
    ):
        super().__init__(debug_mode=debug_mode, sector_name="ORCHESTRATOR")
        self.store = store
        self.identity = identity or get_wearer_identity()

        self.last_input_time = time.time()
        self.chunk_counter = 0
        self.main_task = None  # Track the main loop

        # Milestone 3.1: Context Ring Buffer & Multimodal Telemetry
        self.ring_buffer = ContextRingBuffer(capacity=ring_buffer_capacity)
        self.latest_telemetry: Optional[LocationTelemetry] = None

        # Speaker identity (`tagged-utterance`, ~1 s after its utterance): tag cache + waiters
        self.speaker_tag_wait: float = settings.bee_speaker_tag_wait_seconds
        self._speaker_tags: "OrderedDict[str, SpeakerMatch]" = OrderedDict()
        self._tag_waiters: Dict[str, asyncio.Event] = {}
        # Utterance receive time (epoch) by id, to measure the tag lag; ids already analysed by the pipeline
        self._received_epoch: "OrderedDict[str, float]" = OrderedDict()
        self._analysed: "OrderedDict[str, str]" = OrderedDict()  # utterance id → source key
        self._tag_lags: "deque[float]" = deque(maxlen=200)
        self._side_tasks: "set[asyncio.Task]" = set()
        # True while run() reads the stream concurrently with the utterance worker (tags can arrive)
        self._concurrent_reader = False

        # Bee uuid ↔ numeric id bridge (`new-utterance-chunks` lists utterance ids with the REST id)
        self._utterance_conversations: "OrderedDict[str, str]" = OrderedDict()
        self._conversation_ids: Dict[str, int] = {}

        # Location polling (`bee locations current`): last accepted fix id, wake-up on new conversations
        self.location_poll_seconds: float = settings.bee_location_poll_seconds
        self._last_location_fix_id: Any = None
        self._location_poke: Optional[asyncio.Event] = None
        self._seen_conversations: set = set()
        self.bee: Optional[BeeClient] = None

        # Deep Topic Event Engine (macro events, segments, synthesis scheduling)
        self.engine_enabled = settings.event_engine_enabled
        if engine is not None:
            self.engine = engine
        elif store is not None:
            self.engine = EventEngine(store=store, continuity=build_continuity_from_settings())
        else:
            self.engine = get_event_engine()

        # Historical Transcript Backfill: live coverage intervals + per-utterance ingest ledger
        # (docs/next_steps/historical_backfill/02). Callbacks are wired by the serving layer.
        self.on_coverage_gap: Optional[Callable[[CoverageGap], None]] = None
        self.on_coverage_open: Optional[Callable[[CoverageInterval, Optional[CoverageGap]], None]] = None
        self.coverage = CoverageTracker(
            store_getter=lambda: self.store or get_storage_store(),
            on_gap=lambda gap: self.on_coverage_gap(gap) if self.on_coverage_gap else None,
            on_open=lambda iv, gap: self.on_coverage_open(iv, gap) if self.on_coverage_open else None,
        )

        # Live pipeline dispatches in flight: history backfill yields to live while > 0
        self.inflight_dispatches = 0

        # Real-time state & telemetry tracking
        self.is_running = False
        self.last_heartbeat_time: Optional[float] = None
        self.total_utterances_received: int = 0
        self.status = "IDLE"

    def get_status_dict(self) -> dict:
        """Returns a snapshot of the orchestrator liveness, event engine state, and telemetry."""
        now = time.time()
        is_streaming = (
            self.total_utterances_received > 0
            and (now - self.last_input_time < 120.0)
        )
        is_listening = self.is_running and (
            self.last_heartbeat_time is not None or (now - self.last_input_time < 300.0)
        )

        status_label = "STREAMING" if is_streaming else ("LISTENING" if is_listening else ("STANDBY" if self.is_running else "STOPPED"))
        return {
            "running": self.is_running,
            "status": status_label,
            "mode": "ambient_sse",
            "chunks_screened": self.chunk_counter,
            "utterances_received": self.total_utterances_received,
            "last_heartbeat": self.last_heartbeat_time,
            "last_input_time": self.last_input_time,
            "has_location": self.latest_telemetry is not None,
            "location_place": self.latest_telemetry.place_name if self.latest_telemetry else None,
            "stream_transport": self.bee.active_transport if self.bee else None,
            **self.identity.status(),
            "speaker_tag_lag_seconds": round(statistics.median(self._tag_lags), 2) if self._tag_lags else None,
            "speaker_tag_wait_seconds": self.speaker_tag_wait,
            "event_engine": self.engine.status_summary() if self.engine_enabled else None,
            "coverage": {
                "live_since": self.coverage.current.start if self.coverage.current else None,
                "connected": self.coverage.current is not None,
            },
            "detail": f"Orchestrator {status_label.lower()}; {self.chunk_counter} chunks screened",
        }

    def update_location(self, location_data: dict) -> LocationTelemetry:
        """Parses and updates the latest spatial telemetry from an update-location event."""
        lat = float(location_data.get("latitude", 0.0))
        lon = float(location_data.get("longitude", 0.0))
        place = location_data.get("name") or location_data.get("address") or location_data.get("place_name")
        # No Bee source exposes an accuracy today; kept for other sources and the simulator
        accuracy = location_data.get("horizontal_accuracy") or location_data.get("accuracy_meters")
        extra = {"captured_at": location_data["captured_at"]} if location_data.get("captured_at") else {}

        telemetry = LocationTelemetry(
            latitude=lat,
            longitude=lon,
            place_name=place,
            accuracy_meters=float(accuracy) if accuracy is not None else None,
            **extra,
        )
        self.latest_telemetry = telemetry
        self.debug(
            f"📍 Telemetry updated: ({lat:.4f}, {lon:.4f}) | Zone: '{telemetry.semantic_zone}' | Place: '{place}'",
            log=False,  # location is personal data
        )
        if self.engine_enabled:
            try:
                self.engine.on_location(telemetry.model_dump())
            except Exception as e:
                self.warn(f"Event engine location error: {type(e).__name__}: {e}", "event_engine.task_failed", error=e)
        return telemetry

    def patch_diarization(
        self,
        utterance_id: str,
        speaker_id: Optional[str],
        speaker_role: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Retrospectively patches speaker info (late `tagged-utterance`) in ring buffer and store."""
        role = speaker_role or self.identity.role_for(speaker_id)
        patched_buffer = self.ring_buffer.patch_speaker(
            chunk_id=utterance_id, speaker_id=speaker_id, speaker_role=role, conv_id=session_id
        )
        try:
            store = self.store or get_storage_store()
            store.patch_utterance_speaker(chunk_id=utterance_id, speaker_id=speaker_id, speaker_role=role)
        except Exception as e:
            self.warn(f"Store speaker patch error: {type(e).__name__}: {e}", "storage.write_failed", error=e)
        self.debug(f"🎙️ Diarization patched: Chunk '{utterance_id}' -> '{speaker_id}' ({role})", log=False)
        return patched_buffer

    def buffer_incoming_utterance(self, utterance_data: dict) -> Optional[UtteranceChunk]:
        """Synchronously parses, attaches current telemetry, and pushes utterance to the ring buffer."""
        conv_uuid = utterance_data.get("conversation_uuid") or utterance_data.get("session_id") or "default_session"
        text = (utterance_data.get("text") or "").strip()
        if not text:
            return None
        # Stable fallback id (not time.time()) so a re-delivered utterance keeps its identity
        chunk_id = str(
            utterance_data.get("id")
            or utterance_data.get("chunk_id")
            or stable_chunk_id(conv_uuid, utterance_data.get("received_at"), text)
        )

        speaker = utterance_data.get("speaker") or utterance_data.get("speaker_id")
        speaker_role = utterance_data.get("speaker_role")
        speaker_source = utterance_data.get("speaker_source")
        if not speaker_role or speaker_role == "unknown":
            # Live Bee utterances carry no speaker: identity arrives later as tagged-utterance
            named = self.identity.match_name(speaker, source="internal") if speaker else UNTAGGED
            speaker_role, speaker_source = named.role, speaker_source or named.source
        elif not speaker_source:
            speaker_source = "internal"

        # Best-known utterance time: spoken_at (Bee) > received_at (BeeClient) > now
        spoken_at = utterance_data.get("spoken_at")
        received_at = utterance_data.get("received_at")
        timestamp = spoken_at or received_at or datetime.now().isoformat()

        chunk = UtteranceChunk(
            chunk_id=chunk_id,
            conversation_uuid=conv_uuid,
            text=text,
            speaker_id=speaker,
            speaker_role=speaker_role,
            timestamp=timestamp,
            received_at=received_at,
            spoken_at=spoken_at,
            location=self.latest_telemetry.model_dump() if self.latest_telemetry else None,
            source_key=utterance_data.get("source_key") or live_source_key(conv_uuid, chunk_id),
            bee_conversation_id=self._conversation_ids.get(conv_uuid),
            duration_ms=utterance_data.get("duration_ms"),
            speaker_source=speaker_source,
        )
        tag = self._speaker_tags.get(chunk_id)
        if tag is not None:
            self._apply_match(chunk, tag)
        _remember(self._received_epoch, chunk_id, _epoch(received_at))
        self.ring_buffer.push(chunk)
        return chunk

    async def process_incoming_utterance(self, utterance_data: dict) -> Optional[dict]:
        """Processes an incoming utterance: buffers context, screens, feeds the event engine, and routes."""
        chunk = self.buffer_incoming_utterance(utterance_data)
        if not chunk:
            return None

        self.chunk_counter += 1
        conv_uuid = chunk.conversation_uuid
        chunk_id = chunk.chunk_id

        # Retrieve lightweight context for gatekeeper
        historical_context = self.ring_buffer.get_concatenated_context_text(conv_uuid, exclude_current=True)
        rolling_hint = self.ring_buffer.get_rolling_summary_hint(conv_uuid)

        # Gatekeeper evaluation
        active_task_titles = []
        try:
            store = self.store or get_storage_store()
            active_task_titles = [t.title for t in store.list_planned_tasks(status="pending") if t.title]
        except Exception:
            pass

        # While an event is open, tell the gatekeeper what it is about (raises deep_topic recall)
        event_hint = self.engine.active_event_hint() if self.engine_enabled else ""
        prior_context = "\n".join(part for part in (rolling_hint, event_hint) if part) or None

        async with llm_slot():  # shared across users (MAX_CONCURRENT_LLM_CALLS)
            classification = await aclassify_chunk(
                transcript=chunk.text,
                active_tasks=active_task_titles if active_task_titles else None,
                prior_context=prior_context,
            )
        chunk.categories = list(classification.categories)

        # Feed the event engine BEFORE the pipeline, so a chunk that opens an event is already
        # event-managed when its micro-events are persisted.
        event_id: Optional[str] = None
        if self.engine_enabled:
            try:
                # May call the embedding model / LLM judge: keep it off the event loop
                outcome = await asyncio.to_thread(self.engine.record_chunk, chunk)
                event_id = outcome.event_id
                for t in outcome.transitions:
                    self.debug(f"Event {t.rule}: -> {t.to_status} ({t.reason})")
            except Exception as e:
                self.warn(f"Event engine record_chunk error: {type(e).__name__}: {e}", "event_engine.task_failed",
                          error=e)

        if is_noop(classification):
            self.debug(f"Chunk '{chunk_id}' screened -> DROPPED (noop)")
            self._record_ledger(chunk, "screened_noop")
            return None

        self.debug(f"Chunk '{chunk_id}' screened -> QUALIFIED {classification.categories}")
        await self._await_speaker_tag(chunk)

        # Dispatch with full context to pipeline
        payload = {
            "raw_transcript": chunk.text,
            "historical_context": historical_context,
            "categories": classification.categories,
            "confidence": classification.confidence,
            "summary_hint": classification.summary_hint,
            "location": chunk.location,
            "speaker": chunk.speaker_id,
            "speaker_role": chunk.speaker_role,
            "speaker_score": chunk.speaker_score,
            "speaker_source": chunk.speaker_source,
            "utterance_id": chunk.chunk_id,
            "session_id": event_id or chunk.conversation_uuid,
            "timestamp": chunk.timestamp,
            "event_managed": event_id is not None,
            "source_key": chunk.source_key,
            "ingest_source": "live",
            # The tenant must travel with the payload: a remote AgentCore runtime has no request context
            "user_id": get_tenant_id(),
        }

        try:
            from src.pipeline.remote import invoke_pipeline
            # The pipeline call is synchronous (in-process or AgentCore): keep it off the event loop
            self.inflight_dispatches += 1
            metrics.incr("pipeline.dispatches", get_tenant_id())
            try:
                async with llm_slot():
                    result = await asyncio.to_thread(invoke_pipeline, payload)
            finally:
                self.inflight_dispatches -= 1
                _remember(self._analysed, chunk.chunk_id, chunk.source_key or "")
            # A tag that arrived while the pipeline ran: correct what it extracted
            late = self._speaker_tags.get(chunk.chunk_id)
            if late is not None and chunk.speaker_source not in ("bee_voice_id", "bee_name"):
                await asyncio.to_thread(self.reconcile_speaker, chunk.source_key, late)
        except Exception as e:
            self.warn(f"Pipeline dispatch error: {type(e).__name__}: {e}", "pipeline.dispatch_failed",
                      level=logging.ERROR, error=e, session_id=payload.get("session_id"))
            self._record_ledger(chunk, "failed")
            return None
        failed = isinstance(result, dict) and result.get("status") == "error"
        if failed:
            self.warn(f"Pipeline returned an error: {result.get('error') or 'unknown'}", "pipeline.dispatch_failed",
                      level=logging.ERROR, session_id=payload.get("session_id"))
        self._record_ledger(chunk, "failed" if failed else "qualified")
        return result

    def _record_ledger(self, chunk: UtteranceChunk, status: str) -> None:
        """Ledger evidence that this utterance was analysed (or failed and must be retried)."""
        self.coverage.record_utterance(failed=status == "failed")
        try:
            store = self.store or get_storage_store()
            store.record_ingested_utterance(ledger_entry_for_chunk(chunk, status, source="live"))
        except NotImplementedError:
            pass
        except Exception as e:
            self.warn(f"Ingest ledger write error: {type(e).__name__}: {e}", "storage.write_failed", error=e)

    # ------------------------------------------------------------------
    # Speaker identity (tagged-utterance)
    # ------------------------------------------------------------------

    def on_tagged_utterance(self, data: dict) -> None:
        """Binds a Bee speaker tag to its utterance: wakes a waiting dispatch, or corrects a finished one."""
        uid = str(data.get("utterance_id") or "")
        name = (data.get("person_first_name") or "").strip()
        person_id = data.get("person_id")
        if not uid or (not name and person_id is None):
            return
        match = self.identity.match_tag(person_id=person_id, name=name, score=data.get("speaker_score"))
        _remember(self._speaker_tags, uid, match)
        received = self._received_epoch.get(uid)
        if received is not None:
            self._tag_lags.append(max(0.0, time.time() - received))
        metrics.incr("speaker.tags", get_tenant_id())
        if match.is_wearer:
            metrics.incr("speaker.wearer_tags", get_tenant_id())
        waiter = self._tag_waiters.get(uid)
        if waiter is not None:
            waiter.set()
            return
        self.patch_diarization(uid, match.name or "Unknown", speaker_role=match.role,
                               session_id=data.get("conversation_uuid"))
        source_key = self._analysed.get(uid)
        if source_key:
            # Already analysed with an unknown speaker: fix the entities it produced
            self._run_off_loop(self.reconcile_speaker, source_key, match)

    def _apply_match(self, chunk: UtteranceChunk, match: SpeakerMatch) -> None:
        chunk.speaker_id = match.name or chunk.speaker_id
        chunk.speaker_role = match.role
        chunk.speaker_person_id = match.person_id
        chunk.speaker_score = match.score
        chunk.speaker_source = match.source

    async def _await_speaker_tag(self, chunk: UtteranceChunk) -> None:
        """Before dispatch, waits (bounded) for the utterance's tagged-utterance and applies it."""
        tag = self._speaker_tags.get(chunk.chunk_id)
        if tag is None and self._concurrent_reader and self.speaker_tag_wait > 0:
            received = _epoch(chunk.received_at)
            remaining = received + self.speaker_tag_wait - time.time()
            if remaining > 0:
                waiter = self._tag_waiters.setdefault(chunk.chunk_id, asyncio.Event())
                try:
                    await asyncio.wait_for(waiter.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass
                finally:
                    self._tag_waiters.pop(chunk.chunk_id, None)
                tag = self._speaker_tags.get(chunk.chunk_id)
        if tag is not None:
            self._apply_match(chunk, tag)

    def _run_off_loop(self, fn: Callable[..., Any], *args: Any) -> None:
        """Runs blocking store work in a thread when an event loop is running (tenant context is copied)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            fn(*args)
            return
        task = loop.create_task(asyncio.to_thread(fn, *args))
        self._side_tasks.add(task)  # keep a reference until done (the loop holds tasks weakly)
        task.add_done_callback(self._side_tasks.discard)

    def reconcile_speaker(self, source_key: Optional[str], match: SpeakerMatch) -> Dict[str, int]:
        """Applies a late speaker tag to the action and task extracted from that utterance.

        A contact's completed action no longer counts as the user's (revoked, and a task it completed is
        reopened); a task a contact voiced is cancelled. Entities ids are derived from the source key."""
        out = {"actions": 0, "tasks": 0}
        if not source_key:
            return out
        from src.pipeline.nodes.persist import derived_entity_id

        speaker = SpeakerAttribution(role=match.role, name=match.name, score=match.score, source=match.source)
        try:
            store = self.store or get_storage_store()
            action_id = derived_entity_id(source_key, "action")
            action = store.get_verified_action(action_id) if action_id else None
            if action is not None:
                revoke = match.role == "contact" and not action.is_revoked
                store.set_action_speaker(action_id, speaker, revoke=revoke)
                out["actions"] = 1
                if revoke and action.matched_task_id:
                    task = store.get_planned_task(action.matched_task_id)
                    if task is not None and task.verified_action_id == action_id and task.status == "completed":
                        task.status, task.completed_at, task.verified_action_id = "pending", None, None
                        store.update_planned_task(task)
            task_id = derived_entity_id(source_key, "task")
            task = store.get_planned_task(task_id) if task_id else None
            if task is not None:
                task.speaker = speaker
                if match.role == "contact" and task.status == "pending" and task.origin == "ambient_voice":
                    task.status = "cancelled"
                store.update_planned_task(task)
                out["tasks"] = 1
        except Exception as e:
            self.warn(f"Speaker reconcile error: {type(e).__name__}: {e}", "storage.write_failed", error=e)
        if out["actions"] or out["tasks"]:
            self.debug(f"Late speaker tag applied ({match.role}): {out}", log=False)
        return out

    # ------------------------------------------------------------------
    # Bee conversation identity (uuid ↔ numeric id)
    # ------------------------------------------------------------------

    def on_utterance_chunks(self, data: dict) -> None:
        """`new-utterance-chunks` is the only live event with the numeric conversation id."""
        conv_id = data.get("conversation_id")
        try:
            conv_id = int(conv_id)
        except (TypeError, ValueError):
            return
        conv_uuid = next(
            (self._utterance_conversations[u] for u in data.get("utterance_ids") or [] if u in self._utterance_conversations),
            None,
        )
        if not conv_uuid or self._conversation_ids.get(conv_uuid) == conv_id:
            return
        self._conversation_ids[conv_uuid] = conv_id
        try:
            (self.store or get_storage_store()).map_bee_conversation(conv_uuid, conv_id)
        except NotImplementedError:
            pass
        except Exception as e:
            self.debug(f"Conversation map error: {e}")
        if self.engine_enabled:
            self.engine.register_bee_conversation(conv_id, conv_uuid)

    def _note_utterance(self, data: dict) -> None:
        self.total_utterances_received += 1
        self.last_input_time = time.time()
        self.status = "STREAMING"
        uid = str(data.get("id") or "")
        conv_uuid = data.get("conversation_uuid")
        if uid and conv_uuid:
            _remember(self._utterance_conversations, uid, conv_uuid)
        if conv_uuid and conv_uuid not in self._seen_conversations:
            self._seen_conversations.add(conv_uuid)
            if self._location_poke is not None:
                self._location_poke.set()  # new conversation: Bee samples a fresh location fix

    # ------------------------------------------------------------------
    # Location polling (the Apple Watch emits no update-location)
    # ------------------------------------------------------------------

    async def _fetch_location(self) -> Optional[dict]:
        return await BeeClient(debug_mode=self.debug_mode).get_location()

    async def poll_location(self) -> Optional[LocationTelemetry]:
        """Applies the last Bee fix if it is recent and new; returns the telemetry it produced."""
        try:
            fix = await self._fetch_location()
        except Exception as e:
            self.warn(f"Location poll error: {type(e).__name__}: {e}", "bee.command_failed", command="locations")
            return None
        if not fix or not fix.get("is_recent"):
            return None
        if fix.get("id") is not None and fix.get("id") == self._last_location_fix_id:
            return None
        self._last_location_fix_id = fix.get("id")
        return self.update_location({
            "latitude": fix["latitude"],
            "longitude": fix["longitude"],
            "address": fix.get("address"),
            "captured_at": normalize_bee_time(fix.get("created_at")),
        })

    async def _location_poll_loop(self) -> None:
        assert self._location_poke is not None
        while True:
            await self.poll_location()
            try:
                await asyncio.wait_for(self._location_poke.wait(), timeout=self.location_poll_seconds)
            except asyncio.TimeoutError:
                pass
            self._location_poke.clear()

    # ------------------------------------------------------------------
    # Event routing
    # ------------------------------------------------------------------

    async def handle_event(self, event: dict) -> Optional[Any]:
        """Dispatches an incoming stream event to the appropriate handler."""
        evt_type = event.get("event")
        data = event.get("data", {})

        if evt_type in ("stream-ping", "stream-connected"):
            self.last_heartbeat_time = time.time()
            return None
        if evt_type == "update-location":
            return self.update_location(data)
        elif evt_type == "tagged-utterance":
            return self.on_tagged_utterance(data)
        elif evt_type == "new-utterance-chunks":
            return self.on_utterance_chunks(data)
        elif evt_type in ("new-conversation", "update-conversation", "update-conversation-summary"):
            conv = data.get("conversation") if isinstance(data.get("conversation"), dict) else {}
            if conv.get("uuid") and conv.get("id") is not None:
                try:
                    self._conversation_ids[str(conv["uuid"])] = int(conv["id"])
                    (self.store or get_storage_store()).map_bee_conversation(str(conv["uuid"]), int(conv["id"]))
                except (NotImplementedError, ValueError, TypeError):
                    pass
                except Exception as e:
                    self.debug(f"Conversation map error: {e}")
            if self.engine_enabled:
                try:
                    await asyncio.to_thread(self.engine.on_bee_conversation, evt_type, data)
                except Exception as e:
                    self.warn(f"Event engine conversation event error: {type(e).__name__}: {e}",
                              "event_engine.task_failed", error=e)
            return None
        elif evt_type == "stream-disconnected":
            self.coverage.mark_disconnected()
            return None
        elif evt_type == "new-utterance":
            self._note_utterance(data)
            return await self.process_incoming_utterance(data)
        return None

    async def _utterance_worker(self, queue: "asyncio.Queue[dict]") -> None:
        """Processes utterances one at a time, in arrival order, while the reader keeps consuming."""
        while True:
            data = await queue.get()
            try:
                await self.process_incoming_utterance(data)
            except Exception as e:
                self.warn(f"Utterance processing error: {type(e).__name__}: {e}", "orchestrator.utterance_failed",
                          level=logging.ERROR, error=e)
            finally:
                queue.task_done()

    async def run(self):
        """Main loop: reads the stream and hands utterances to a sequential worker.

        Reading never waits for screening or the pipeline, so `tagged-utterance`, pings and conversation
        events are applied while an utterance is still being processed.
        """
        self.main_task = asyncio.current_task()
        self.is_running = True
        self.status = "LISTENING"

        runtime: Optional[EventEngineRuntime] = None
        if self.engine_enabled:
            if self.engine is get_event_engine():
                from src.ingestion.event_engine import get_event_engine_runtime
                runtime = get_event_engine_runtime()
            else:
                runtime = EventEngineRuntime(self.engine)
            runtime.ensure_started()

        self.debug("Starting Bee stream ingestion...")
        self.bee = BeeClient(debug_mode=self.debug_mode)
        self.coverage.recover_after_crash()
        await self.identity.ensure_loaded()

        queue: "asyncio.Queue[dict]" = asyncio.Queue()
        background = [asyncio.create_task(self._utterance_worker(queue))]
        if self.location_poll_seconds > 0:
            self._location_poke = asyncio.Event()
            background.append(asyncio.create_task(self._location_poll_loop()))
        self._concurrent_reader = True

        try:
            async for event in self.bee.stream_events():
                evt_name = event.get('event')
                self.debug(f"⚡ Received event: {evt_name}")
                if evt_name != "stream-disconnected":
                    self.coverage.mark_alive()
                if evt_name == "new-utterance":
                    self._note_utterance(event.get("data", {}))
                    await queue.put(event.get("data", {}))
                    continue
                await self.handle_event(event)
        except asyncio.CancelledError:
            pass
        finally:
            self._concurrent_reader = False
            for task in background:
                task.cancel()
            await asyncio.gather(*background, return_exceptions=True)
            self._location_poke = None
            self.coverage.mark_disconnected()
            self.is_running = False
            self.status = "STOPPED"
            self.bee.stop()

    async def shutdown(self):
        """Safely triggers cancellation of the main run loop only."""
        if self.main_task and not self.main_task.done():
            self.main_task.cancel()


async def main(orchestrator_instance):
    """Bootstraps the event loop and attaches OS signal handlers."""
    loop = asyncio.get_running_loop()

    # Catch OS signals (e.g. from Docker/Colima) to trigger graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(orchestrator_instance.shutdown())
        )

    await orchestrator_instance.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bee Stream Ingestion Orchestrator")
    parser.add_argument(
        '--debug',
        type=str,
        default="none",
        help="Specify debug sector: 'all', 'bee', 'orchestrator', or 'none'"
    )
    args = parser.parse_args()

    orchestrator = BeeStreamOrchestrator(debug_mode=args.debug)

    try:
        asyncio.run(main(orchestrator))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nOrchestrator stopped gracefully.")

"""Replay of Deep Topic Event Engine scenarios with a virtual clock (doc 07 §2.2).

Used by tests (heuristic similarity, fake synthesis) and by scripts/replay_event_scenarios.py
(real embeddings, threshold calibration).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.schemas import UtteranceChunk
from src.ingestion.event_engine import EventEngine, Transition, to_iso

SCENARIOS_PATH = Path(__file__).resolve().parent.parent.parent / "resources" / "event_scenarios.json"
REPLAY_T0 = datetime(2026, 10, 13, 9, 0, 0).timestamp()


def load_event_scenarios(path: Path = SCENARIOS_PATH) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["scenarios"]


@dataclass
class ReplayResult:
    scenario_id: str
    event_ids: List[str]
    utterance_events: List[Optional[str]]           # event id each utterance ended up in
    transitions: List[Transition] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def replay_scenario(engine: EventEngine, scenario: Dict[str, Any], t0: float = REPLAY_T0,
                    run_jobs: bool = True) -> ReplayResult:
    """Feeds the scenario utterances with periodic ticks, then lets every timer expire."""
    cfg = engine.config
    tick = cfg.tick_seconds
    transitions: List[Transition] = []
    chunk_ids: List[str] = []
    last_tick = t0

    def _tick_until(target: float) -> None:
        nonlocal last_tick
        while last_tick + tick <= target:
            last_tick += tick
            transitions.extend(engine.tick(now=last_tick))

    for i, utt in enumerate(scenario["utterances"]):
        ts = t0 + float(utt["offset"])
        _tick_until(ts)
        chunk = UtteranceChunk(
            chunk_id=f"{scenario['id']}-{i:03d}",
            conversation_uuid=utt.get("conversation_uuid", "replay"),
            text=utt["text"],
            timestamp=to_iso(ts),
            categories=list(utt.get("categories") or []),
            location=utt.get("location"),
        )
        chunk_ids.append(chunk.chunk_id)
        transitions.extend(engine.record_chunk(chunk).transitions)

    end = t0 + float(scenario["utterances"][-1]["offset"]) + cfg.t_soft + cfg.t_hard + 2 * tick + 120
    _tick_until(end)
    if run_jobs:
        engine.run_pending_jobs_sync()

    # Where did each utterance end up? (session_chunks is the source of truth after moves)
    store = engine.store
    owner: Dict[str, str] = {}
    event_ids: List[str] = []
    for dossier in sorted(store.list_session_dossiers(limit=100), key=lambda d: d.start_time):
        if not dossier.segments:
            continue
        event_ids.append(dossier.session_id)
        for c in store.list_session_chunks(dossier.session_id):
            owner[c.chunk_id] = dossier.session_id
    utterance_events = [owner.get(cid) for cid in chunk_ids]

    result = ReplayResult(scenario["id"], event_ids, utterance_events, transitions)
    result.errors = check_expectations(scenario, result, store)
    return result


def check_expectations(scenario: Dict[str, Any], result: ReplayResult, store: Any) -> List[str]:
    errors: List[str] = []
    expect = scenario.get("expect", {})
    if "events" in expect and len(result.event_ids) != expect["events"]:
        errors.append(f"expected {expect['events']} events, got {len(result.event_ids)}")

    label_to_event: Dict[str, str] = {}
    event_to_label: Dict[str, str] = {}
    for utt, event_id in zip(scenario["utterances"], result.utterance_events):
        label = utt.get("expected_event")
        if not label:
            continue
        if event_id is None:
            errors.append(f"utterance at +{utt['offset']}s ({label}) not assigned to any event")
            continue
        if label_to_event.setdefault(label, event_id) != event_id:
            errors.append(f"utterance at +{utt['offset']}s split from the rest of {label}")
        if event_to_label.setdefault(event_id, label) != label:
            errors.append(f"utterance at +{utt['offset']}s ({label}) merged into {event_to_label[event_id]}")

    if "segments" in expect and not errors:
        for event_id, n_expected in zip(result.event_ids, expect["segments"]):
            dossier = store.get_session_dossier(event_id)
            n = len(dossier.segments) if dossier else 0
            if n != n_expected:
                errors.append(f"event {event_id[:8]}: expected {n_expected} segments, got {n}")
    return errors

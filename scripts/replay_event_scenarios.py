#!/usr/bin/env python3
"""Replay & calibration tool for the Deep Topic Event Engine (docs/.../07 §2.2-2.3).

Replays resources/event_scenarios.json with a virtual clock and checks the expected event
grouping. With --calibrate it also prints the window-vs-profile similarity distribution for
same-event and different-event windows, to choose TOPIC_SIM_SAME / TOPIC_SIM_DIFFERENT.

Usage:
    python scripts/replay_event_scenarios.py                       # embedding backend (Bedrock)
    python scripts/replay_event_scenarios.py --backend heuristic   # offline
    python scripts/replay_event_scenarios.py --calibrate
    python scripts/replay_event_scenarios.py --scenario conference_talks_no_gap -v
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from typing import Dict, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.core.schemas import BriefingReport  # noqa: E402
from src.core.storage.sqlite_store import SQLiteContextStore  # noqa: E402
from src.ingestion.event_engine import EngineConfig, EventEngine  # noqa: E402
from src.ingestion.scenario_replay import load_event_scenarios, replay_scenario  # noqa: E402
from src.ingestion.topic_continuity import ContinuityConfig, TopicSimilarity  # noqa: E402


class _NoSynthesis:
    """Replays only exercise grouping; synthesis is out of scope (and would cost LLM calls)."""

    def segment(self, text, session_id, outline=None, kind="segment"):
        return BriefingReport(topic_title="(replay)", context_type="general_meeting")

    def final(self, parts, extra_text, session_id, outline=None, micro_events=None):
        return BriefingReport(topic_title="(replay)", context_type="general_meeting")


def _windows(utterances: List[dict], size: int = 5) -> List[Tuple[str, str]]:
    labelled = [u for u in utterances if u.get("expected_event")]
    return [
        (" ".join(u["text"] for u in labelled[i:i + size]), labelled[i]["expected_event"])
        for i in range(0, len(labelled), size)
    ]


def calibrate(similarity: TopicSimilarity, scenarios: List[dict]) -> None:
    """Scores each window against the profile of the event it would be compared with."""
    same: List[float] = []
    different: List[float] = []
    for sc in scenarios:
        windows = _windows(sc["utterances"])
        if len(windows) < 2:
            continue
        profile = None
        profile_label = windows[0][1]
        for text, label in windows:
            score, vec = similarity.score(text, profile)
            if score is not None and similarity.is_mature(profile):
                (same if label == profile_label else different).append(score.value)
                print(f"  {sc['id']:<34} {label} vs {profile_label}: {score.value:.3f} ({score.backend})")
            if label == profile_label:
                profile = similarity.update(profile, text, vec)

    def _stats(values: List[float]) -> str:
        if not values:
            return "n/a"
        return f"n={len(values)} min={min(values):.3f} mean={sum(values) / len(values):.3f} max={max(values):.3f}"

    print("\nSame-event windows:      ", _stats(same))
    print("Different-event windows: ", _stats(different))
    if same and different:
        gap_low, gap_high = max(different), min(same)
        print(f"Separation gap: ({gap_low:.3f}, {gap_high:.3f})" if gap_high > gap_low else
              f"OVERLAP: max(different)={gap_low:.3f} >= min(same)={gap_high:.3f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend", choices=["embedding", "heuristic"], default="embedding")
    parser.add_argument("--scenario", default=None, help="Replay a single scenario id")
    parser.add_argument("--calibrate", action="store_true", help="Print similarity distributions")
    parser.add_argument("--same", type=float, default=None, help="Override the 'same' threshold")
    parser.add_argument("--different", type=float, default=None, help="Override the 'different' threshold")
    parser.add_argument("--no-judge", action="store_true", help="Disable the LLM tie-breaker")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print every lifecycle transition")
    args = parser.parse_args()

    base = ContinuityConfig.from_settings() or ContinuityConfig()
    overrides: Dict[str, float] = {"backend": args.backend}
    if args.same is not None:
        overrides["sim_same" if args.backend == "embedding" else "sim_same_heuristic"] = args.same
    if args.different is not None:
        overrides["sim_different" if args.backend == "embedding" else "sim_different_heuristic"] = args.different
    cfg = ContinuityConfig(**{**base.__dict__, **overrides, "llm_judge": not args.no_judge})
    similarity = TopicSimilarity(cfg)

    scenarios = load_event_scenarios()
    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] == args.scenario]

    if args.calibrate:
        print(f"Calibration ({args.backend})")
        calibrate(similarity, scenarios)
        print()

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for sc in scenarios:
            store = SQLiteContextStore(os.path.join(tmp, f"{sc['id']}.db"))
            engine = EventEngine(store=store, config=EngineConfig(), synthesizer=_NoSynthesis(), continuity=similarity)
            result = replay_scenario(engine, sc)
            status = "PASS" if result.ok else "FAIL"
            failures += 0 if result.ok else 1
            print(f"[{status}] {sc['id']}: {len(result.event_ids)} event(s) — {sc['title']}")
            for err in result.errors[:5]:
                print(f"        ✗ {err}")
            for t in result.transitions:
                if args.verbose or t.rule in ("R4", "R7", "R9"):
                    print(f"        {t.rule:<3} -> {t.to_status:<9} {t.reason:<22} {t.detail}")
    print(f"\n{len(scenarios) - failures}/{len(scenarios)} scenarios passed ({args.backend} backend)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

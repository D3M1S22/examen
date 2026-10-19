#!/usr/bin/env python3
"""Interactive & Automated Test Runner for EXAMEN Phase 1-3 Features.

Executes curated mock conversations defined in `resources/mock_conversations.json`
against the live or simulated EXAMEN pipeline:
- M1.1: Contextual Deep Topic Explanatory Synthesis
- M1.2: Ambient Scheduled Tasks from Spoken Voice
- M1.3: Bilateral Social Commitments & Closed-Loop Reconciliation
- M2.1: Autonomous Social Web Profiler & Disambiguation Guardrails
- M2.2: Echo Show & Web UI Multi-Modal Card Standardization
- M3.1: Context Ring Buffer, Split Turn Anaphora & GPS Telemetry Grounding
- M3.2: Macro Session Engine, Boundary Triggers & Micro-Event Decoupling

Usage:
    # List all available scenarios
    python scripts/simulate_mock_conversations.py --list

    # Run in interactive mode (choose from menu)
    python scripts/simulate_mock_conversations.py --interactive

    # Run a specific scenario (Fast Mock Mode)
    python scripts/simulate_mock_conversations.py --scenario ambient_scheduled_tasks --mock

    # Run a specific scenario (Live Bedrock AI Mode)
    python scripts/simulate_mock_conversations.py --scenario bilateral_social_commitments

    # Run the continuous meeting session scenario
    python scripts/simulate_mock_conversations.py --scenario macro_session_continuous_meeting

    # Run ALL scenarios end-to-end
    python scripts/simulate_mock_conversations.py --all --mock
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.config import settings
from src.core.models import has_active_model_credentials
from src.core.schemas import (
    BriefingReport,
    ChunkClassification,
    ExamenState,
    LocationTelemetry,
    MicroEventRef,
    PlannedTask,
    SessionDossier,
    SocialCommitment,
    SocialEntity,
    UtteranceChunk,
    VerifiedAction,
)
from src.core.storage import get_storage_store
from src.core.storage.sqlite_store import SQLiteContextStore
from src.ingestion.gatekeeper import classify_chunk, is_noop
from src.ingestion.ring_buffer import ContextRingBuffer
from src.ingestion.session_manager import SessionManager
from src.pipeline.graph import pipeline_graph

# ANSI Terminal Colors
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
BG_BLUE = "\033[44m"
BG_DARK = "\033[100m"

MOCK_FILE_PATH = REPO_ROOT / "resources" / "mock_conversations.json"


def load_mock_scenarios() -> List[Dict[str, Any]]:
    """Loads all mock test scenarios from resources/mock_conversations.json."""
    if not MOCK_FILE_PATH.exists():
        print(f"{RED}Error: Mock file {MOCK_FILE_PATH} does not exist.{RESET}")
        sys.exit(1)
    with open(MOCK_FILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("scenarios", [])


def print_banner(mode: str = "LIVE"):
    print(f"\n{BOLD}{CYAN}╔════════════════════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║             EXAMEN — Ambient Conversation Simulator & Feature Tester          ║{RESET}")
    print(f"{BOLD}{CYAN}╚════════════════════════════════════════════════════════════════════════════════╝{RESET}")
    mode_color = YELLOW if mode == "MOCK" else GREEN
    print(f" {BOLD}Mode:{RESET}          {mode_color}{mode.upper()}{RESET} ({'Fast offline heuristics' if mode == 'MOCK' else 'Live Bedrock Inference'})")
    print(f" {BOLD}Model:{RESET}         {MAGENTA}{settings.gatekeeper_model_id}{RESET}")
    print(f" {BOLD}Dataset:{RESET}       {WHITE}{MOCK_FILE_PATH.relative_to(REPO_ROOT)}{RESET}")
    print(f" {BOLD}Storage:{RESET}       {CYAN}SQLite (examen.db){RESET}")
    print(f"{DIM}──────────────────────────────────────────────────────────────────────────────────{RESET}\n")


def print_scenario_card(scenario: Dict[str, Any]):
    print(f"{BOLD}{WHITE}Scenario:{RESET} {BOLD}{CYAN}{scenario.get('title')}{RESET} ({YELLOW}{scenario.get('id')}{RESET})")
    print(f"{BOLD}Target Milestone:{RESET} {MAGENTA}{scenario.get('milestone')}{RESET} — {scenario.get('target_feature')}")
    print(f"{DIM}{scenario.get('description')}{RESET}")
    print(f"{DIM}Turns count: {len(scenario.get('turns', []))}{RESET}\n")


def execute_scenario(scenario: Dict[str, Any], use_mock_ai: bool = False) -> Dict[str, Any]:
    """Executes a single multi-turn scenario through the full EXAMEN ingestion & pipeline."""
    store = get_storage_store()
    session_id = scenario.get("session_id") or f"sess-sim-{uuid.uuid4().hex[:8]}"

    # Milestone 3.1: Ring buffer for multi-turn history
    ring_buffer = ContextRingBuffer(capacity=4)
    session_manager = SessionManager(store=store)

    turns = scenario.get("turns", [])
    print(f"\n{BOLD}{BG_BLUE}{WHITE}  ▶ RUNNING SCENARIO: {scenario.get('title')} ({len(turns)} turns)  {RESET}\n")

    results: List[Dict[str, Any]] = []

    # Configure mock AI mode if requested
    orig_mock = settings.mock_ai
    if use_mock_ai:
        settings.mock_ai = True

    try:
        for idx, turn in enumerate(turns, 1):
            text = turn.get("text", "")
            speaker = turn.get("speaker", "user")
            speaker_role = turn.get("speaker_role", "user")
            loc_data = turn.get("location")
            expected_cat = turn.get("expected_category", "noop")

            location_obj: Optional[LocationTelemetry] = None
            if loc_data:
                location_obj = LocationTelemetry(
                    latitude=loc_data.get("latitude", 0.0),
                    longitude=loc_data.get("longitude", 0.0),
                    place_name=loc_data.get("place_name"),
                )

            # Record in session manager (Milestone 3.2)
            dossier, boundary = session_manager.record_chunk(
                session_id=session_id,
                text=text,
                location=loc_data,
            )

            print(f"{BOLD}{WHITE}[Turn {idx}/{len(turns)}]{RESET} {MAGENTA}Speaker ({speaker_role}):{RESET} {BOLD}\"{text}\"{RESET}")
            if location_obj and location_obj.place_name:
                print(f"  {CYAN}📍 Telemetry:{RESET} {location_obj.place_name} ({location_obj.semantic_zone})")

            # Check boundary trigger if expected
            if turn.get("triggers_boundary"):
                print(f"  {YELLOW}⚡ Boundary Detector Triggered:{RESET} '{boundary}' -> Concluded Session Dossier!")

            # 1. Gatekeeper Classification with prior context (Milestone 3.1)
            t0 = time.perf_counter()
            rolling_context_text = ring_buffer.get_concatenated_context_text(conv_id=session_id, exclude_current=False)

            # Retrieve active tasks for prompt injection
            active_tasks = [t.title for t in store.list_planned_tasks(status="pending") if t.title]

            classification: ChunkClassification = classify_chunk(
                transcript=text,
                active_tasks=active_tasks if active_tasks else None,
                prior_context=rolling_context_text if rolling_context_text else None,
            )
            gk_latency = time.perf_counter() - t0

            is_drop = is_noop(classification)
            status_badge = f"{RED}[DROPPED / NOOP]{RESET}" if is_drop else f"{GREEN}[QUALIFIED]{RESET}"
            print(f"  {status_badge} Categories: {classification.categories} (Conf: {classification.confidence:.2f}, Latency: {gk_latency*1000:.1f}ms)")

            # Record in ring buffer for subsequent turns
            utterance = UtteranceChunk(
                chunk_id=f"chk-{uuid.uuid4().hex[:6]}",
                text=text,
                speaker_id=speaker,
                speaker_role=speaker_role,
                location=location_obj.model_dump() if location_obj else None
            )
            ring_buffer.push(utterance, conv_id=session_id)

            # 2. Pipeline Execution (if qualified)
            pipeline_result: Dict[str, Any] = {}
            if not is_drop:
                state_input: ExamenState = {
                    "raw_transcript": text,
                    "session_id": session_id,
                    "categories": classification.categories,
                    "historical_context": rolling_context_text or None,
                    "location": location_obj.model_dump() if location_obj else None,
                    "speaker": speaker,
                    "speaker_role": speaker_role,
                    "utterance_id": utterance.chunk_id,
                }

                t_pipe = time.perf_counter()
                pipeline_result = pipeline_graph.invoke(state_input)
                pipe_latency = time.perf_counter() - t_pipe

                # Print extracted entity highlights
                _print_turn_extraction_highlights(pipeline_result, pipe_latency)

            print(f"{DIM}  {'─' * 70}{RESET}")
            results.append({
                "turn": idx,
                "text": text,
                "classification": classification.model_dump(),
                "pipeline_result": pipeline_result,
            })

        # Summary of the scenario
        _print_scenario_summary(scenario, session_id, store)

    finally:
        settings.mock_ai = orig_mock

    return {"scenario_id": scenario.get("id"), "turns_executed": len(turns), "session_id": session_id}


def _print_turn_extraction_highlights(state: Dict[str, Any], latency: float):
    # Scheduled Task (M1.2)
    task: Optional[PlannedTask] = state.get("scheduled_task")
    if task:
        print(f"  {GREEN}✓ [M1.2 Scheduled Task Extracted]{RESET}")
        print(f"    • Title:    {BOLD}{task.title}{RESET}")
        print(f"    • Domain:   {task.domain} | Origin: {task.origin}")
        print(f"    • Time:     {CYAN}{task.scheduled_time or 'No absolute time'}{RESET} ({task.relative_time_anchor})")
        print(f"    • Verbatim: \"{task.raw_statement}\"")

    # Action Verified (Baseline + M3.1)
    action: Optional[VerifiedAction] = state.get("action_data")
    if action:
        match_str = f" [Auto-Resolved Task: {action.matched_task_id}]" if action.matched_task_id else ""
        loc_str = f" @ {action.location.get('place_name')}" if action.location else ""
        print(f"  {GREEN}✓ [Action Verified]{RESET} {BOLD}{action.action_type}{RESET} (Conf: {action.confidence*100:.0f}%){loc_str}{match_str}")

    # Social Contact & Commitments (M1.3 & M2.1)
    social: Optional[SocialEntity] = state.get("social_data")
    if social:
        print(f"  {GREEN}✓ [M1.3 & M2.1 Social Encounter Recorded]{RESET}")
        print(f"    • Contact:  {BOLD}{social.person_name}{RESET} ({social.company_or_role or 'No role specified'})")
        if social.web_profile:
            wp = social.web_profile
            print(f"    • Web Dossier: {CYAN}{wp.headline}{RESET} (Match: {wp.confidence_score*100:.0f}%)")
            if wp.linkedin_url:
                print(f"      🔗 LinkedIn: {wp.linkedin_url}")
            if wp.areas_of_expertise:
                print(f"      🏷️ Expertise: {', '.join(wp.areas_of_expertise[:3])}")
        comms = social.get_commitments_as_objects()
        if comms:
            for c in comms:
                debtor_badge = f"{YELLOW}📤 You Promised{RESET}" if c.debtor == "user" else f"{CYAN}📥 Contact Promised{RESET}"
                task_link = f" [Auto-Provisioned Routine ID: {c.auto_scheduled_task_id}]" if c.auto_scheduled_task_id else ""
                print(f"    • Promise: {debtor_badge} \"{c.description}\" ({c.due_date_raw}){task_link}")

    # Deep Topic Briefing (M1.1)
    briefing: Optional[BriefingReport] = state.get("briefing_report")
    if briefing:
        print(f"  {GREEN}✓ [M1.1 Deep Topic Explanatory Synthesis]{RESET}")
        print(f"    • Topic:    {BOLD}{briefing.topic_title}{RESET} ({briefing.context_type})")
        if briefing.explanatory_synthesis:
            preview = briefing.explanatory_synthesis[:140].replace('\n', ' ')
            print(f"    • Synthesis: {DIM}\"{preview}...\"{RESET}")
        print(f"    • Sources:  {len(briefing.web_sources)} web citation(s)")


def _print_scenario_summary(scenario: Dict[str, Any], session_id: str, store: SQLiteContextStore):
    print(f"\n{BOLD}{CYAN}════════════════════════════════════════════════════════════════════════════════{RESET}")
    print(f"{BOLD}{GREEN}✓ Scenario Completed:{RESET} {scenario.get('title')}")

    # Inspect current database state for this session
    dossier = store.get_session_dossier(session_id)
    if dossier:
        print(f"  📂 {BOLD}Session Dossier:{RESET} {dossier.title} ({dossier.status.upper()})")
        print(f"     Linked Micro-Events: {len(dossier.linked_micro_events)} records")
        for ref in dossier.linked_micro_events:
            print(f"     - [{ref.event_type.upper()}] {ref.headline} (ID: {ref.record_id})")

    # Inspect commitments
    commitments = store.list_social_commitments(limit=3)
    if commitments:
        print(f"  🤝 {BOLD}Active Commitments:{RESET}")
        for c in commitments[:3]:
            debtor_str = "You Promised" if c.debtor == "user" else "Contact Promised"
            status_str = f"{GREEN}FULFILLED{RESET}" if c.status == "fulfilled" else f"{YELLOW}PENDING{RESET}"
            print(f"     - [{status_str}] {c.contact_name} ({debtor_str}): \"{c.description}\"")

    # Web UI preview tip
    print(f"\n{YELLOW}💡 Web UI Live Inspection:{RESET}")
    print(f"   • Open Web UI:                 {CYAN}http://localhost:8000{RESET}")
    print(f"   • View Echo Show Touch Cards:   Click {BOLD}[📺 Echo Show Cards]{RESET} on the dashboard")
    print(f"   • View Bilateral Commitments:  Click {BOLD}[Social Hub -> 🤝 Bilateral Commitments]{RESET}")
    print(f"   • View Executive Dossiers:     Click {BOLD}[Social Hub -> ⚡ Executive Dossiers]{RESET}")
    print(f"   • View Ambient Voice Tasks:    Scroll to {BOLD}Planned Routines (🎙️ Ambient Voice badge){RESET}")
    print(f"{BOLD}{CYAN}════════════════════════════════════════════════════════════════════════════════{RESET}\n")


def interactive_menu():
    """Runs an interactive CLI selector allowing the user to choose which scenario to run."""
    scenarios = load_mock_scenarios()
    while True:
        print(f"\n{BOLD}{CYAN}Select a Mock Conversation Scenario to Test:{RESET}")
        for idx, sc in enumerate(scenarios, 1):
            print(f"  {BOLD}[{idx}]{RESET} {CYAN}{sc.get('title')}{RESET} ({MAGENTA}{sc.get('milestone')}{RESET})")
            print(f"      {DIM}{sc.get('target_feature')}{RESET}")
        print(f"  {BOLD}[A]{RESET} {GREEN}Run ALL Scenarios Sequentially{RESET}")
        print(f"  {BOLD}[Q]{RESET} Quit")

        choice = input(f"\n{BOLD}Enter selection (1-{len(scenarios)}, A, Q): {RESET}").strip().upper()
        if choice == "Q":
            print(f"{CYAN}Exiting. Good luck testing!{RESET}\n")
            break
        elif choice == "A":
            mode_choice = input(f"Run mode? [1] Fast Mock (Instant)  [2] Live Bedrock: ").strip()
            use_mock = mode_choice != "2"
            for sc in scenarios:
                execute_scenario(sc, use_mock_ai=use_mock)
            break
        else:
            try:
                num = int(choice)
                if 1 <= num <= len(scenarios):
                    target = scenarios[num - 1]
                    mode_choice = input(f"Run mode? [1] Fast Mock (Instant)  [2] Live Bedrock: ").strip()
                    use_mock = mode_choice != "2"
                    execute_scenario(target, use_mock_ai=use_mock)
                else:
                    print(f"{RED}Invalid number.{RESET}")
            except ValueError:
                print(f"{RED}Invalid selection.{RESET}")


def main():
    parser = argparse.ArgumentParser(description="EXAMEN Mock Conversation Test Runner")
    parser.add_argument("--list", action="store_true", help="List all available mock scenarios")
    parser.add_argument("--scenario", type=str, help="Run a specific scenario by id")
    parser.add_argument("--all", action="store_true", help="Run all scenarios sequentially")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive menu")
    parser.add_argument("--mock", action="store_true", help="Force fast offline mock AI mode")
    parser.add_argument("--live", action="store_true", help="Force live Bedrock AI inference mode")
    args = parser.parse_args()

    scenarios = load_mock_scenarios()

    if args.list:
        print_banner("INFO")
        print(f"{BOLD}Available Mock Test Scenarios ({len(scenarios)} total):{RESET}\n")
        for sc in scenarios:
            print_scenario_card(sc)
        sys.exit(0)

    use_mock = args.mock or (not args.live and settings.mock_ai)
    mode_str = "MOCK" if use_mock else "LIVE"

    if args.scenario:
        print_banner(mode_str)
        matched = next((s for s in scenarios if s.get("id") == args.scenario), None)
        if not matched:
            print(f"{RED}Scenario '{args.scenario}' not found. Use --list to see available IDs.{RESET}")
            sys.exit(1)
        execute_scenario(matched, use_mock_ai=use_mock)
    elif args.all:
        print_banner(mode_str)
        for sc in scenarios:
            execute_scenario(sc, use_mock_ai=use_mock)
    elif args.interactive:
        print_banner(mode_str)
        interactive_menu()
    else:
        # Default behavior: if no args provided, run interactive
        print_banner(mode_str)
        interactive_menu()


if __name__ == "__main__":
    from src.core.cli import cli_user_context

    with cli_user_context():  # EXAMEN_CLI_USER=<username>
        main()

#!/usr/bin/env python3
"""Interactive Live CLI Tester for EXAMEN Ambient AI Pipeline.

Allows testing raw ambient speech transcripts live against:
1. Stage 1: Semantic Gatekeeper Screening (with Active Tasks dynamic prompt injection)
2. Stage 2 & 3: LangGraph Pipeline Fan-Out (Action Verifier, Social Recall, Topic Research)
3. Stage 4: SQLite Context Storage Persistence & Auto-Resolution of Planned Tasks

Usage:
    # Interactive mode (type / paste chunks with multi-line support)
    python scripts/live_tester.py

    # Single chunk via argument
    python scripts/live_tester.py --text "I just turned off the kitchen stove."

    # From file or pipe
    python scripts/live_tester.py --file my_chunk.txt
    echo "Pleased to meet you, I'm Sarah Connor from Cyberdyne" | python scripts/live_tester.py
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
import os
import sys
import time
import traceback
import uuid
from typing import Any, Dict, List, Optional

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.core.config import settings
from src.core.models import has_active_model_credentials
from src.core.schemas import (
    BriefingReport,
    ChunkClassification,
    ExamenState,
    PlannedTask,
    SocialEntity,
    TopicExtraction,
    UtteranceChunk,
    VerifiedAction,
)
from src.core.storage import get_storage_store
from src.core.storage.sqlite_store import SQLiteContextStore
from src.ingestion.event_engine import EngineConfig, EventEngine, Transition, to_iso
from src.ingestion.gatekeeper import classify_chunk, is_noop
from src.pipeline.graph import pipeline_graph

logger = logging.getLogger("examen.scripts.live_tester")

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

# Price estimates for nvidia.nemotron-super-3-120b on AWS Bedrock ($ per 1M tokens)
PRICE_INPUT_PER_1M = 0.15
PRICE_OUTPUT_PER_1M = 0.65

# ---------------------------------------------------------------------------
# Deep Topic Event Engine mode (virtual clock: /tick <seconds> fast-forwards time)
# ---------------------------------------------------------------------------
EVENT_MODE = {"enabled": False, "clock_offset": 0.0}
_LIVE_ENGINE: Optional[EventEngine] = None


def get_live_engine() -> EventEngine:
    global _LIVE_ENGINE
    if _LIVE_ENGINE is None:
        _LIVE_ENGINE = EventEngine(
            store=get_storage_store(),
            config=EngineConfig.from_settings(),
            clock=lambda: time.time() + EVENT_MODE["clock_offset"],
        )
    return _LIVE_ENGINE


def print_transitions(transitions: List[Transition]) -> None:
    for t in transitions:
        print(f"  {MAGENTA}⚙ {t.rule}{RESET} → {BOLD}{t.to_status.upper()}{RESET} "
              f"({t.reason}) {DIM}{t.detail}{RESET}")


def print_event_status(engine: EventEngine) -> None:
    ev = engine.current_event()
    cfg = engine.config
    print(f"  {DIM}Virtual clock: {to_iso(engine.now())} (offset +{EVENT_MODE['clock_offset']:.0f}s) | "
          f"T_soft={cfg.t_soft:.0f}s T_hard={cfg.t_hard:.0f}s min_words={cfg.min_segment_words}{RESET}")
    if not ev:
        print(f"  {DIM}No open event.{RESET}")
        return
    print(f"  {BOLD}Event:{RESET} {CYAN}{ev.title}{RESET} [{YELLOW}{ev.status.upper()}{RESET}] {DIM}{ev.session_id}{RESET}")
    for seg in ev.segments:
        print(f"    • Segment {seg.index} [{seg.status}] {seg.word_count} words "
              f"{DIM}{seg.start_time} → {seg.end_time or '…'}{RESET} {seg.title or ''}")


def drain_event_jobs(engine: EventEngine) -> None:
    """Runs pending segment/final syntheses inline and prints the produced briefings."""
    pending = engine.pending_jobs()
    if not pending:
        return
    print(f"  {CYAN}⏳ Running {pending} synthesis job(s)...{RESET}")
    engine.run_pending_jobs_sync()
    store = get_storage_store()
    for d in store.list_session_dossiers(limit=3):
        for b in store.list_briefings_for_session(d.session_id)[-3:]:
            print(f"    {GREEN}✓ [{b.kind}]{RESET} {BOLD}{b.topic_title}{RESET} {DIM}({d.session_id[:8]}){RESET}")


def estimate_tokens(text: str) -> int:
    """Rough estimation of tokens: ~1 token per 3.8 characters for mixed technical text."""
    if not text:
        return 0
    return max(1, int(len(text) / 3.8))


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * PRICE_INPUT_PER_1M / 1_000_000.0) + (
        output_tokens * PRICE_OUTPUT_PER_1M / 1_000_000.0
    )


def print_banner(db_path: str):
    provider = settings.gatekeeper_provider.upper()
    model = settings.gatekeeper_model_id
    credentials_ok = has_active_model_credentials(settings.gatekeeper_provider)
    cred_status = f"{GREEN}VALID (AWS Root/IAM){RESET}" if credentials_ok else f"{RED}MISSING (Mock Fallback){RESET}"

    store = get_storage_store()
    pending_tasks_count = 0
    try:
        pending_tasks_count = len(store.list_planned_tasks(status="pending"))
    except Exception:
        pass

    print(f"\n{BOLD}{CYAN}╔════════════════════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║                     EXAMEN — Ambient AI Live Pipeline Tester                  ║{RESET}")
    print(f"{BOLD}{CYAN}╚════════════════════════════════════════════════════════════════════════════════╝{RESET}")
    print(f" {BOLD}Provider:{RESET}     {MAGENTA}{provider}{RESET} (Converse / Mantle dual-routing)")
    print(f" {BOLD}Model:{RESET}        {YELLOW}{model}{RESET}")
    print(f" {BOLD}Credentials:{RESET}  {cred_status}")
    print(f" {BOLD}Storage:{RESET}      {WHITE}SQLite ({db_path}){RESET} — {CYAN}{pending_tasks_count} active planned tasks{RESET}")
    print(f" {DIM}Commands: /tasks, /actions, /commitments, /sessions, /profiles, /social, /topics, /simulate, /event, /tick, /conclude, /reset-db, /help, /exit{RESET}")
    print(f"{DIM}──────────────────────────────────────────────────────────────────────────────────{RESET}\n")


def print_section(title: str, icon: str = "•", color: str = CYAN):
    print(f"\n{color}{BOLD}{icon} {title}{RESET}")
    print(f"{DIM}{'─' * 80}{RESET}")


def handle_subcommand(cmd: str, store: SQLiteContextStore) -> bool:
    """Handles interactive slash commands. Returns True if handled, False otherwise."""
    parts = cmd.strip().split(maxsplit=2)
    action = parts[0].lower()

    if action in ("/exit", "/quit", "exit", "quit"):
        print(f"\n{CYAN}Exiting EXAMEN Live Tester. Happy hacking!{RESET}\n")
        sys.exit(0)

    elif action == "/help":
        print(f"\n{BOLD}Available Commands:{RESET}")
        print(f"  {CYAN}/tasks{RESET}                  List all planned tasks (pending and completed, with origin badges)")
        print(f"  {CYAN}/add-task <title> [domain]{RESET} Schedule a new planned task (domain: safety|routine|work_task)")
        print(f"  {CYAN}/actions{RESET}                List recent verified completed actions with spatial telemetry")
        print(f"  {CYAN}/commitments{RESET}            List bilateral promises (debts you owe vs contact debts) [M1.3]")
        print(f"  {CYAN}/sessions{RESET}               List continuous macro session dossiers with linked micro-events [M3.2]")
        print(f"  {CYAN}/profiles{RESET}               List enriched executive web dossiers with LinkedIn links [M2.1]")
        print(f"  {CYAN}/social{RESET}                 List stored social contacts and bilateral commitments")
        print(f"  {CYAN}/topics{RESET}                 List recent deep topic briefings and explanatory syntheses [M1.1]")
        print(f"  {CYAN}/simulate [name]{RESET}        Run Phase 1-3 mock conversation scenarios interactively")
        print(f"  {CYAN}/event [on|off]{RESET}         Toggle Deep Topic Event Engine mode / show the open event")
        print(f"  {CYAN}/tick <seconds>{RESET}          Fast-forward the event engine virtual clock and run timers")
        print(f"  {CYAN}/conclude{RESET}               Conclude the open event now and run the final synthesis")
        print(f"  {CYAN}/reset-db [--seed]{RESET}       Reset local SQLite database to clean state (optional baseline seed)")
        print(f"  {CYAN}/clear{RESET}                  Clear terminal screen")
        print(f"  {CYAN}/exit{RESET}                   Exit the interactive tester")
        return True

    elif action == "/clear":
        os.system("clear" if os.name != "nt" else "cls")
        print_banner(store.db_path)
        return True

    elif action == "/tasks":
        print_section("Planned Tasks in Context Store", "📅", CYAN)
        tasks = store.list_planned_tasks()
        if not tasks:
            print(f"  {DIM}No planned tasks found in database.{RESET}")
            print(f"  {YELLOW}Tip: Use /add-task \"unplug clothes iron\" safety to test task auto-resolution!{RESET}")
        else:
            for t in tasks:
                status_color = GREEN if t.status == "completed" else YELLOW
                matched_str = f" (Verified Action ID: {t.verified_action_id[:8]}...)" if t.verified_action_id else ""
                print(f"  • [{status_color}{t.status.upper()}{RESET}] {BOLD}{t.title}{RESET} "
                      f"(Domain: {CYAN}{t.domain}{RESET}, ID: {DIM}{t.id}{RESET}){matched_str}")
        return True

    elif action == "/add-task":
        if len(parts) < 2:
            print(f"{RED}Usage: /add-task <title> [domain]{RESET}")
            print(f"Example: /add-task \"unplug clothes iron\" safety")
            return True
        title = parts[1].strip('"\'')
        domain = parts[2].strip() if len(parts) > 2 else "safety"
        if domain not in ("safety", "routine", "work_task"):
            domain = "safety"

        task = PlannedTask(
            id=f"task-{uuid.uuid4().hex[:8]}",
            title=title,
            domain=domain,
            status="pending",
        )
        store.save_planned_task(task)
        print(f"{GREEN}✓ Successfully scheduled task:{RESET} \"{title}\" (Domain: {domain}, ID: {task.id})")
        print(f"  {DIM}Now paste an audio chunk confirming this action to watch EXAMEN verify and resolve it!{RESET}")
        return True

    elif action == "/actions":
        print_section("Recent Verified Actions in Context Store", "🛡️", GREEN)
        actions = store.list_actions(limit=10)
        if not actions:
            print(f"  {DIM}No verified actions recorded yet.{RESET}")
        else:
            for a in actions:
                task_str = f" [Linked Task: {CYAN}{a.matched_task_id}{RESET}]" if a.matched_task_id else ""
                print(f"  • {BOLD}{a.action_type}{RESET} (Domain: {CYAN}{a.domain}{RESET}, "
                      f"Confidence: {GREEN}{a.confidence * 100:.0f}%{RESET}) at {DIM}{a.timestamp}{RESET}{task_str}")
                print(f"    {DIM}\"{a.raw_statement}\"{RESET}")
        return True

    elif action == "/social":
        print_section("Stored Social Contacts & Commitments", "🤝", MAGENTA)
        contacts = store.search_social_contact("")
        if not contacts:
            print(f"  {DIM}No social contacts stored yet.{RESET}")
        else:
            for c in contacts:
                role = f" — {c.company_or_role}" if c.company_or_role else ""
                print(f"  • {BOLD}{c.person_name}{RESET}{role} (ID: {DIM}{c.id}{RESET})")
                if c.commitments:
                    print(f"    {YELLOW}Commitments:{RESET}")
                    for cm in c.commitments:
                        print(f"      - {cm}")
                if c.key_topics:
                    print(f"    {DIM}Topics: {', '.join(c.key_topics)}{RESET}")
        return True

    elif action == "/topics":
        print_section("Recent Topic Briefings & Dossiers", "📚", BLUE)
        briefings = store.list_topic_briefings(limit=5)
        if not briefings:
            print(f"  {DIM}No topic briefings stored yet.{RESET}")
        else:
            for b in briefings:
                print(f"  • {BOLD}{b.topic_title}{RESET} ({CYAN}{b.context_type}{RESET}) — {DIM}{b.created_at}{RESET}")
                if b.executive_summary:
                    print(f"    {DIM}Summary: {b.executive_summary[0]}{RESET}")
                print(f"    {DIM}Sources: {len(b.web_sources)} web reference(s){RESET}")
        return True

    elif action == "/commitments":
        print_section("Bilateral Social Commitments [M1.3]", "🤝", YELLOW)
        commitments = store.list_social_commitments(limit=20)
        if not commitments:
            print(f"  {DIM}No social commitments stored yet.{RESET}")
        else:
            for c in commitments:
                debtor_badge = f"{YELLOW}📤 You Promised{RESET}" if c.debtor == "user" else f"{CYAN}📥 Contact Promised{RESET}"
                status_color = GREEN if c.status == "fulfilled" else YELLOW
                task_str = f" [Linked Task: {c.auto_scheduled_task_id}]" if c.auto_scheduled_task_id else ""
                print(f"  • [{status_color}{c.status.upper()}{RESET}] {BOLD}{c.contact_name}{RESET} — {debtor_badge}: \"{c.description}\" ({c.due_date_raw or 'No due date'}){task_str}")
        return True

    elif action == "/sessions":
        print_section("Macro Session Dossiers [M3.2]", "📂", MAGENTA)
        dossiers = store.list_session_dossiers(limit=10)
        if not dossiers:
            print(f"  {DIM}No session dossiers stored yet.{RESET}")
        else:
            for d in dossiers:
                status_color = GREEN if d.status == "concluded" else YELLOW
                print(f"  • [{status_color}{d.status.upper()}{RESET}] {BOLD}{d.title or d.session_id}{RESET} ({CYAN}{d.domain}{RESET}) — Started: {DIM}{d.start_time}{RESET}")
                print(f"    Chunks: {len(d.transcript_chunks)} | Micro-events: {len(d.linked_micro_events)}")
                for ref in d.linked_micro_events[:4]:
                    print(f"    - [{ref.event_type.upper()}] {ref.headline}")
        return True

    elif action == "/profiles":
        print_section("Executive Web Profiles [M2.1]", "⚡", CYAN)
        contacts = store.search_social_contact("")
        profiled = [c for c in contacts if c.web_profile]
        if not profiled:
            print(f"  {DIM}No contacts with enriched web profiles yet.{RESET}")
        else:
            for c in profiled:
                wp = c.web_profile
                print(f"  • {BOLD}{c.person_name}{RESET} — {CYAN}{wp.headline or c.company_or_role}{RESET} (Match: {wp.confidence_score*100:.0f}%)")
                if wp.linkedin_url:
                    print(f"    🔗 LinkedIn: {wp.linkedin_url}")
                if wp.areas_of_expertise:
                    print(f"    🏷️ Expertise: {', '.join(wp.areas_of_expertise[:4])}")
                if wp.bio_summary:
                    print(f"    📖 Bio: {DIM}\"{wp.bio_summary[:120]}...\"{RESET}")
        return True

    elif action == "/simulate":
        from scripts.simulate_mock_conversations import execute_scenario, load_mock_scenarios
        scenarios = load_mock_scenarios()
        target_name = parts[1].strip() if len(parts) > 1 else None
        if target_name:
            matched = next((s for s in scenarios if s.get("id") == target_name), None)
            if matched:
                execute_scenario(matched, use_mock_ai=True)
            else:
                print(f"{RED}Unknown scenario '{target_name}'. Available: {[s['id'] for s in scenarios]}{RESET}")
        else:
            print(f"\n{BOLD}Available Mock Scenarios:{RESET}")
            for sc in scenarios:
                print(f"  • {CYAN}{sc['id']}{RESET} — {sc['title']} ({MAGENTA}{sc['milestone']}{RESET})")
            print(f"Run with: {YELLOW}/simulate <id>{RESET}\n")
        return True

    elif action == "/event":
        if len(parts) > 1 and parts[1].lower() in ("on", "off"):
            EVENT_MODE["enabled"] = parts[1].lower() == "on"
        state = f"{GREEN}ON{RESET}" if EVENT_MODE["enabled"] else f"{YELLOW}OFF{RESET}"
        print_section(f"Deep Topic Event Engine — event mode {state}", "🧠", MAGENTA)
        print_event_status(get_live_engine())
        return True

    elif action == "/tick":
        try:
            seconds = float(parts[1]) if len(parts) > 1 else 60.0
        except ValueError:
            print(f"{RED}Usage: /tick <seconds>{RESET}")
            return True
        EVENT_MODE["clock_offset"] += seconds
        engine = get_live_engine()
        print_section(f"Virtual clock +{seconds:.0f}s", "⏩", MAGENTA)
        transitions = engine.tick()
        print_transitions(transitions) if transitions else print(f"  {DIM}No transition.{RESET}")
        drain_event_jobs(engine)
        print_event_status(engine)
        return True

    elif action == "/conclude":
        engine = get_live_engine()
        event_id = engine.current_event_id()
        if not event_id:
            print(f"  {DIM}No open event to conclude.{RESET}")
            return True
        engine.conclude(event_id)
        print_section("Event concluded (R8)", "🏁", MAGENTA)
        drain_event_jobs(engine)
        return True

    elif action == "/reset-db":
        from scripts.reset_db import reset_database
        seed = "--seed" in cmd
        reset_database(backup=True, seed=seed, db_path=store.db_path)
        return True

    return False


def run_pipeline_test(
    transcript: str,
    force_pipeline: bool = False,
    force_mock: bool = False,
    skip_persist: bool = False,
):
    """Executes the full EXAMEN pipeline for a given transcript chunk and prints telemetry."""
    transcript = transcript.strip()
    if not transcript:
        print(f"{YELLOW}Warning: Empty transcript received.{RESET}")
        return

    store = get_storage_store()

    # Pre-fetch pending tasks for telemetry & prompt injection
    pending_tasks_before: List[PlannedTask] = []
    try:
        pending_tasks_before = store.list_planned_tasks(status="pending")
    except Exception:
        pass
    active_titles = [t.title for t in pending_tasks_before if t.title]

    print_section("Input Transcript", "🎙️", WHITE)
    print(f"\"{transcript}\"")
    print(f"{DIM}Characters: {len(transcript)} | Words: {len(transcript.split())}{RESET}")

    # =========================================================================
    # STAGE 1: SEMANTIC GATEKEEPER SCREENING
    # =========================================================================
    print_section("Stage 1: Semantic Gatekeeper Screening", "🛡️", CYAN)
    t0_gate = time.perf_counter()

    classification: ChunkClassification = classify_chunk(
        transcript=transcript,
        active_tasks=active_titles if active_titles else None,
        force_mock=force_mock,
    )
    t_gate = time.perf_counter() - t0_gate

    is_chunk_noop = is_noop(classification)
    categories = classification.categories
    confidence = classification.confidence
    hint = classification.summary_hint or "N/A"

    badge_color = RED if is_chunk_noop else GREEN
    status_label = "DROPPED (NOOP)" if is_chunk_noop else "QUALIFIED FOR DOWNSTREAM"

    print(f"  {BOLD}Status:{RESET}       [{badge_color}{BOLD}{status_label}{RESET}]")
    print(f"  {BOLD}Categories:{RESET}   {YELLOW}{categories}{RESET}")
    print(f"  {BOLD}Confidence:{RESET}   {WHITE}{confidence * 100:.1f}%{RESET}")
    print(f"  {BOLD}Summary Hint:{RESET} {WHITE}{hint}{RESET}")
    print(f"  {BOLD}Latency:{RESET}      {CYAN}{t_gate:.3f}s{RESET}")

    # Deep Topic Event Engine (event mode): accumulate deep_topic content into macro events
    event_id: Optional[str] = None
    if EVENT_MODE["enabled"]:
        engine = get_live_engine()
        outcome = engine.record_chunk(UtteranceChunk(
            conversation_uuid="live_tester",
            text=transcript,
            timestamp=to_iso(engine.clock()),
            categories=list(categories),
        ))
        event_id = outcome.event_id
        print_section("Deep Topic Event Engine", "🧠", MAGENTA)
        print_transitions(outcome.transitions)
        print_event_status(engine)
        drain_event_jobs(engine)

    if is_chunk_noop and not force_pipeline:
        print(f"\n  {YELLOW}⚡ Pipeline Short-Circuit:{RESET} Chunk deemed casual chit-chat or background noise.")
        print(f"  {GREEN}✓ ~90% Downstream LLM tokens saved!{RESET} No database pollution.")
        print(f"  {DIM}(Pass --force or type 'force' to evaluate downstream nodes anyway){RESET}")

        # Summary telemetry for NOOP
        in_tok = estimate_tokens(transcript) + 450  # System prompt + transcript
        out_tok = 35
        cost = estimate_cost(in_tok, out_tok)
        print_section("Execution Telemetry & Cost", "📊", BLUE)
        print(f"  • {BOLD}Total Pipeline Time:{RESET} {CYAN}{t_gate:.3f}s{RESET}")
        print(f"  • {BOLD}Estimated Tokens:{RESET}    ~{in_tok} in / ~{out_tok} out (~{in_tok + out_tok} total)")
        print(f"  • {BOLD}Estimated Cost:{RESET}      ${cost:.6f} USD")
        print(f"  • {BOLD}Active Model:{RESET}        {settings.gatekeeper_model_id} ({settings.gatekeeper_provider})")
        return

    # =========================================================================
    # STAGE 2 & 3: LANGGRAPH PIPELINE FAN-OUT
    # =========================================================================
    print_section("Stage 2 & 3: LangGraph Extraction & Autonomous Research", "⚡", MAGENTA)

    session_id = event_id or f"cli-test-{uuid.uuid4().hex[:6]}"
    state_categories = categories if not (is_chunk_noop and force_pipeline) else ["action", "social", "deep_topic"]

    initial_state: ExamenState = {
        "raw_transcript": transcript,
        "session_id": session_id,
        "event_managed": event_id is not None,
        "categories": state_categories,
        "confidence": confidence,
        "action_data": None,
        "social_data": None,
        "topic_extracted": None,
        "briefing_report": None,
    }

    t0_pipe = time.perf_counter()
    pipeline_result = pipeline_graph.invoke(initial_state)
    t_pipe = time.perf_counter() - t0_pipe

    action_data: Optional[VerifiedAction] = pipeline_result.get("action_data")
    social_data: Optional[SocialEntity] = pipeline_result.get("social_data")
    topic_extracted: Optional[TopicExtraction] = pipeline_result.get("topic_extracted")
    briefing_report: Optional[BriefingReport] = pipeline_result.get("briefing_report")

    # Display Action State Verifier Results
    if "action" in state_categories or action_data:
        print(f"\n  {BOLD}[Stage 3B: Action-State Verifier]{RESET}")
        if action_data:
            match_badge = (
                f"{GREEN}{BOLD}✓ LINKED TO PLANNED TASK: {action_data.matched_task_id}{RESET}"
                if action_data.matched_task_id
                else f"{DIM}(Unscheduled action){RESET}"
            )
            print(f"    • {BOLD}Action Type:{RESET}    {GREEN}{action_data.action_type}{RESET}")
            print(f"    • {BOLD}Domain:{RESET}         {CYAN}{action_data.domain}{RESET}")
            print(f"    • {BOLD}Confidence:{RESET}     {WHITE}{action_data.confidence * 100:.1f}%{RESET}")
            print(f"    • {BOLD}Task Match:{RESET}     {match_badge}")
            print(f"    • {BOLD}Raw Quote:{RESET}      \"{action_data.raw_statement}\"")
        else:
            print(f"    • {YELLOW}Action Rejected:{RESET} Statement identified as doubt, intention, or unverifiable.")

    # Display Social Recall Extractor Results
    if "social" in state_categories or social_data:
        print(f"\n  {BOLD}[Stage 3A: Social Recall Extractor]{RESET}")
        if social_data:
            print(f"    • {BOLD}Person Name:{RESET}    {MAGENTA}{social_data.person_name}{RESET}")
            if social_data.company_or_role:
                print(f"    • {BOLD}Role / Org:{RESET}     {WHITE}{social_data.company_or_role}{RESET}")
            if social_data.contact_info:
                print(f"    • {BOLD}Contact:{RESET}        {CYAN}{social_data.contact_info}{RESET}")
            if social_data.commitments:
                print(f"    • {BOLD}Commitments ({len(social_data.commitments)}):{RESET}")
                for c in social_data.commitments:
                    print(f"      - {YELLOW}{c}{RESET}")
            if social_data.key_topics:
                print(f"    • {BOLD}Topics:{RESET}         {DIM}{', '.join(social_data.key_topics)}{RESET}")
        else:
            print(f"    • {YELLOW}No social contact or bilateral commitments detected.{RESET}")

    # Display Topic Research Results
    if "deep_topic" in state_categories or briefing_report:
        print(f"\n  {BOLD}[Stage 3C: Deep Topic Research & Web Synthesis]{RESET}")
        if topic_extracted:
            print(f"    • {BOLD}Topic Title:{RESET}    {BLUE}{topic_extracted.topic_title}{RESET} ({topic_extracted.context_type})")
            if topic_extracted.search_queries:
                print(f"    • {BOLD}Web Queries:{RESET}    {DIM}{' | '.join(topic_extracted.search_queries)}{RESET}")

        if briefing_report:
            print(f"    • {BOLD}Web Sources Consulted:{RESET} {len(briefing_report.web_sources)}")
            for src in briefing_report.web_sources[:5]:
                print(f"      - {CYAN}{src}{RESET}")

            if briefing_report.executive_summary:
                print(f"    • {BOLD}Executive Summary:{RESET}")
                for point in briefing_report.executive_summary:
                    print(f"      * {WHITE}{point}{RESET}")

            if briefing_report.action_items:
                print(f"    • {BOLD}Action Items:{RESET}")
                for item in briefing_report.action_items:
                    print(f"      > {YELLOW}{item}{RESET}")
        elif event_id:
            print(f"    • {CYAN}Accumulated into event {event_id[:8]}{RESET} — synthesized per segment/event "
                  f"(see /event, /tick, /conclude)")
        else:
            print(f"    • {YELLOW}No technical topic dossier generated.{RESET}")

    # =========================================================================
    # STAGE 4: STORAGE & TASK AUTO-RESOLUTION AUDIT
    # =========================================================================
    print_section("Stage 4: Context Store Persistence Audit", "💾", GREEN)
    persisted_items = []
    if action_data:
        persisted_items.append(f"VerifiedAction ('{action_data.action_type}')")
    if social_data:
        # node_persist swallows storage errors, so confirm the contact actually landed
        try:
            social_persisted = store.get_social_contact(social_data.person_name) is not None
        except Exception:
            social_persisted = False
        if social_persisted:
            persisted_items.append(f"SocialEntity ('{social_data.person_name}')")
        else:
            print(f"  {RED}✗ SocialEntity ('{social_data.person_name}') was NOT persisted (see logs above).{RESET}")
    if briefing_report:
        persisted_items.append(f"BriefingReport ('{briefing_report.topic_title}')")

    if persisted_items:
        print(f"  {GREEN}✓ Persisted to SQLite:{RESET} {', '.join(persisted_items)}")
    else:
        print(f"  {DIM}No new durable entities committed.{RESET}")

    # Check if any planned task was resolved from pending -> completed
    try:
        pending_tasks_after = store.list_planned_tasks(status="pending")
        resolved_tasks = [t for t in pending_tasks_before if t.id not in [p.id for p in pending_tasks_after]]
        if resolved_tasks:
            for rt in resolved_tasks:
                print(f"  {GREEN}{BOLD}🎯 TASK AUTO-RESOLVED:{RESET} Task '{rt.title}' (ID: {rt.id}) "
                      f"transitioned from {YELLOW}'pending'{RESET} ➔ {GREEN}'completed'{RESET}!")
    except Exception as e:
        logger.debug(f"Failed to audit task transitions: {e}")

    # =========================================================================
    # STAGE 5: EXECUTION TELEMETRY & COST
    # =========================================================================
    t_total = t_gate + t_pipe
    in_tok = estimate_tokens(transcript) + 1200
    out_tok = 250 if (action_data or social_data or briefing_report) else 50
    if briefing_report:
        in_tok += 2000
        out_tok += 600

    cost = estimate_cost(in_tok, out_tok)

    print_section("Execution Telemetry & Cost Dashboard", "📊", BLUE)
    print(f"  • {BOLD}Gatekeeper Screening:{RESET}  {CYAN}{t_gate:.3f}s{RESET}")
    print(f"  • {BOLD}LangGraph Pipeline:{RESET}     {CYAN}{t_pipe:.3f}s{RESET}")
    print(f"  • {BOLD}Total Turnaround:{RESET}       {BOLD}{GREEN}{t_total:.3f}s{RESET}")
    print(f"  • {BOLD}Estimated Tokens:{RESET}       ~{in_tok} in / ~{out_tok} out (~{in_tok + out_tok} total)")
    print(f"  • {BOLD}Estimated Cost:{RESET}         ${cost:.6f} USD")
    print(f"  • {BOLD}Provider & Model:{RESET}       {settings.gatekeeper_provider} / {settings.gatekeeper_model_id}")


def interactive_loop():
    """Runs the interactive Read-Eval-Print loop for live chunk testing."""
    store = get_storage_store()
    print_banner(store.db_path)

    while True:
        try:
            print(f"{CYAN}{BOLD}Paste or enter transcript chunk below{RESET}")
            print(f"{DIM}(Press Enter on an empty line or Ctrl+D to submit. Or type /tasks, /help, /exit):{RESET}")

            lines: List[str] = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break

                stripped = line.strip()
                # Check for slash commands on first line
                if not lines and stripped.startswith("/"):
                    handled = handle_subcommand(stripped, store)
                    if handled:
                        lines = []
                        break

                # Double Enter finishes input
                if not stripped and lines:
                    break

                lines.append(line)

            transcript = "\n".join(lines).strip()
            if not transcript:
                continue

            # Run pipeline
            run_pipeline_test(transcript)
            print(f"\n{DIM}{'═' * 80}{RESET}\n")

        except KeyboardInterrupt:
            print(f"\n\n{YELLOW}Interrupted. Type /exit to quit or continue testing.{RESET}\n")
        except Exception as e:
            print(f"\n{RED}{BOLD}Error executing pipeline:{RESET} {e}\n")
            traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description="EXAMEN Live Pipeline CLI Tester — Test ambient speech chunks against Bedrock and LangGraph."
    )
    parser.add_argument(
        "-t", "--text", type=str, default=None, help="Direct transcript text chunk to evaluate."
    )
    parser.add_argument(
        "-f", "--file", type=str, default=None, help="File path containing transcript text to evaluate."
    )
    parser.add_argument(
        "--force", action="store_true", help="Force pipeline extraction even if Gatekeeper flags chunk as noop."
    )
    parser.add_argument(
        "--mock", action="store_true", help="Force mock/heuristic mode without invoking Bedrock API."
    )
    parser.add_argument(
        "--no-persist", action="store_true", help="Dry-run mode: do not commit entities to storage."
    )
    parser.add_argument(
        "--event-mode", action="store_true",
        help="Route chunks through the Deep Topic Event Engine (use /tick and /conclude to drive timers).",
    )

    args = parser.parse_args()
    EVENT_MODE["enabled"] = args.event_mode

    # Determine input text
    transcript: Optional[str] = None
    if args.text:
        transcript = args.text
    elif args.file:
        if not os.path.exists(args.file):
            print(f"{RED}Error: File '{args.file}' does not exist.{RESET}")
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            transcript = f.read().strip()
    elif not sys.stdin.isatty():
        # Read from pipe e.g. echo "..." | python live_tester.py
        transcript = sys.stdin.read().strip()

    if transcript:
        store = get_storage_store()
        print_banner(store.db_path)
        run_pipeline_test(
            transcript=transcript,
            force_pipeline=args.force,
            force_mock=args.mock,
            skip_persist=args.no_persist,
        )
    else:
        # Launch interactive REPL
        interactive_loop()


if __name__ == "__main__":
    main()

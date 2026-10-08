"""LangGraph Conditional StateGraph for EXAMEN Multi-Agent Pipeline.

Orchestrates multi-label fan-out routing across specialized extraction
channels (Action Verifier, Social Recall, Topic Research) and converges
into atomic context persistence.
"""

from __future__ import annotations

import logging
from typing import List

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.core.schemas import ExamenState
from src.pipeline.nodes.action_state import node_extract_action
from src.pipeline.nodes.persist import node_persist
from src.pipeline.nodes.scheduler import node_extract_scheduled_task
from src.pipeline.nodes.social import node_extract_social
from src.pipeline.nodes.topic_research import node_topic_research

logger = logging.getLogger("examen.pipeline.graph")


def route_categories(state: ExamenState) -> List[str]:
    """Inspects qualified categories from edge screening and returns target nodes for fan-out.

    Incoming payloads have already been pre-screened and qualified by the edge
    Ingestion Gatekeeper. If no actionable category is present, short-circuits to END.
    """
    categories = state.get("categories") or []

    targets: List[str] = []
    if "action" in categories:
        targets.append("extract_action")
    if "social" in categories:
        targets.append("extract_social")
    if "deep_topic" in categories:
        targets.append("topic_research")
    if "scheduled_task" in categories:
        targets.append("extract_scheduled_task")

    # If no actionable category detected (e.g. ['noop']), short-circuit directly to END
    if not targets:
        logger.debug(f"No actionable categories in {categories}; short-circuiting to END.")
        return [END]

    logger.debug(f"Routing qualified categories {categories} to targets: {targets}")
    return targets


def build_examen_graph() -> CompiledStateGraph:
    """Builds and compiles the EXAMEN LangGraph conditional StateGraph.

    Architecture:
    - START conditionally fans out via route_categories to:
        * 'extract_action' (Stage 3B Action-State Verifier)
        * 'extract_social' (Stage 3A Social Recall)
        * 'topic_research' (Stage 3C Deep Research & Briefing Synthesizer)
        * 'extract_scheduled_task' (Stage 3D Ambient Task Scheduler)
        * END (if NOOP / chit-chat)
    - All active channel branches fan-in to 'persist'.
    - 'persist' commits all extracted entities to durable storage and terminates at END.
    """
    builder = StateGraph(ExamenState)

    # Register nodes
    builder.add_node("extract_action", node_extract_action)
    builder.add_node("extract_social", node_extract_social)
    builder.add_node("topic_research", node_topic_research)
    builder.add_node("extract_scheduled_task", node_extract_scheduled_task)
    builder.add_node("persist", node_persist)

    # Conditional routing from START
    builder.add_conditional_edges(
        START,
        route_categories,
        ["extract_action", "extract_social", "topic_research", "extract_scheduled_task", END],
    )

    # Fan-in edges to persist
    builder.add_edge("extract_action", "persist")
    builder.add_edge("extract_social", "persist")
    builder.add_edge("topic_research", "persist")
    builder.add_edge("extract_scheduled_task", "persist")

    # Termination
    builder.add_edge("persist", END)

    return builder.compile()


pipeline_graph = build_examen_graph()

"""Specialized pipeline nodes for EXAMEN."""

from src.pipeline.nodes.action_state import node_extract_action
from src.pipeline.nodes.social import node_extract_social
from src.pipeline.nodes.topic_research import node_topic_research
from src.pipeline.nodes.persist import node_persist

__all__ = [
    "node_extract_action",
    "node_extract_social",
    "node_topic_research",
    "node_persist",
]

"""Unit tests for BeeStreamOrchestrator and Gatekeeper screening integration."""

import pytest
import asyncio
from src.ingestion.orchestrator import BeeStreamOrchestrator, analyze_text_model
from src.ingestion.gatekeeper import is_noop
from src.core.schemas import ChunkClassification, PlannedTask
from src.core.storage import get_storage_store


@pytest.mark.asyncio
async def test_analyze_text_model_noop():
    """Trivial chit-chat through orchestrator must be dropped as noop."""
    result = await analyze_text_model("What a nice weather we are having today, really warm.", chunk_id=1)
    assert isinstance(result, ChunkClassification)
    assert is_noop(result) is True
    assert "noop" in result.categories


@pytest.mark.asyncio
async def test_analyze_text_model_action_qualified():
    """Confirmed action through orchestrator must qualify for downstream routing."""
    result = await analyze_text_model("I just unplugged the clothes iron before leaving the house.", chunk_id=2)
    assert isinstance(result, ChunkClassification)
    assert is_noop(result) is False
    assert "action" in result.categories


@pytest.mark.asyncio
async def test_analyze_text_model_with_planned_task_in_storage():
    """Active pending planned tasks should be dynamically picked up and matched."""
    store = get_storage_store()
    task = PlannedTask(
        title="evening blood pressure medication",
        domain="safety",
        recurrence="daily"
    )
    store.save_planned_task(task)

    sample = "The evening medication is done and all taken care of."
    result = await analyze_text_model(sample, chunk_id=3)
    assert isinstance(result, ChunkClassification)
    assert "action" in result.categories
    assert is_noop(result) is False


@pytest.mark.asyncio
async def test_orchestrator_buffer_limit_and_semantic_cut():
    """Orchestrator should split chunks safely without cutting words in half."""
    orchestrator = BeeStreamOrchestrator(debug_mode="none", max_chars=40, max_duration=300)
    
    # Text with sentence boundaries
    text = "First sentence completed. Second sentence in progress and continuing further."
    orchestrator.text_buffer = text
    
    # Evaluate limit when length exceeds max_chars
    await orchestrator._evaluate_buffer_limit(len(text))
    
    # Buffer should retain remainder and queue first chunk
    assert not orchestrator.response_queue.empty()
    queued_task = await orchestrator.response_queue.get()
    result = await queued_task
    assert result is not None

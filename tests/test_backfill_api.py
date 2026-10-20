"""REST / MCP contracts of the Historical Transcript Backfill (docs/next_steps/historical_backfill/04 §3)."""

import asyncio
from datetime import datetime, timedelta

import pytest
from starlette.testclient import TestClient

import src.core.storage as storage_mod
import src.ingestion.backfill as backfill_mod
from src.core.config import settings
from src.core.schemas import CoverageInterval
from src.core.storage.sqlite_store import SQLiteContextStore
from src.ingestion.backfill import BackfillService
from src.ingestion.bee_history import FixtureBeeHistorySource
from src.serving.mcp_server import create_app
from src.serving.tools.ingestion_tools import execute_get_ingestion_coverage
from tests.test_backfill import StaticSynthesizer, fake_classify, make_conv

NOW = datetime.now().replace(microsecond=0)
START = NOW - timedelta(hours=3)
LINES = [(i * 30, f"I locked the door number {i} of the building") for i in range(4)]


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = SQLiteContextStore(str(tmp_path / "api.db"))
    monkeypatch.setattr(storage_mod, "_store_instance", store)
    monkeypatch.setattr(settings, "mock_ai", True)
    service = BackfillService(
        store_getter=lambda: store,
        source_factory=lambda: FixtureBeeHistorySource([make_conv(30, START, LINES)]),
        executor_options=dict(classify=fake_classify, dispatch=lambda p: {"status": "success"},
                              synthesizer=StaticSynthesizer(), continuity=None),
    )
    monkeypatch.setattr(service, "ensure_started", lambda: True)   # runs are executed explicitly
    monkeypatch.setattr(backfill_mod, "_service", service)
    client = TestClient(create_app())
    return client, store, service


def window(**extra):
    return {"from": (START - timedelta(minutes=5)).isoformat(), "to": (START + timedelta(minutes=30)).isoformat(),
            **extra}


def test_coverage_endpoint_reports_gaps_and_buckets(env):
    client, store, _ = env
    store.save_coverage_interval(CoverageInterval(source="live", start=(NOW - timedelta(hours=6)).isoformat(),
                                                  end=(NOW - timedelta(hours=4)).isoformat()))
    res = client.get("/api/backfill/coverage", params={"from": (NOW - timedelta(hours=6)).isoformat(),
                                                       "to": NOW.isoformat(), "bucket": "hour"})
    assert res.status_code == 200
    data = res.json()
    assert len(data["intervals"]) == 1 and len(data["gaps"]) == 1
    assert data["summary"]["live_seconds"] == pytest.approx(7200, abs=1)
    assert len(data["buckets"]) in (6, 7)


def test_preview_is_free_and_returns_the_plan(env):
    client, _, _ = env
    res = client.post("/api/backfill/preview", json=window())
    assert res.status_code == 200
    plan = res.json()
    assert plan["utterances"]["selected"] == 4 and plan["over_budget"] is False
    # Window screening: 4 utterances fit one window -> 1 window call + the expected drill-down
    assert plan["utterances"]["windows"] == 1
    assert plan["estimate"]["gatekeeper_calls"] < 4


def test_run_lifecycle_over_rest(env):
    client, store, service = env
    res = client.post("/api/backfill/runs", json=window())
    assert res.status_code == 202
    run_id = res.json()["run"]["id"]
    assert client.post("/api/backfill/runs", json=window()).status_code == 409

    asyncio.run(service.run_next())
    detail = client.get(f"/api/backfill/runs/{run_id}").json()
    assert detail["run"]["status"] == "completed"
    assert detail["progress"]["processed"] == 4 and detail["progress"]["progress"] == 1.0
    assert client.get("/api/backfill/runs").json()["count"] == 1
    assert client.get("/api/backfill/runs/missing").status_code == 404

    queued = client.post("/api/backfill/runs", json={"from": (START - timedelta(hours=2)).isoformat(),
                                                     "to": (START - timedelta(hours=1)).isoformat()})
    cancelled = client.post(f"/api/backfill/runs/{queued.json()['run']['id']}/cancel").json()["run"]
    assert cancelled["status"] == "cancelled"


def test_invalid_and_over_budget_requests(env, monkeypatch):
    client, _, _ = env
    bad = client.post("/api/backfill/runs", json={"from": NOW.isoformat(), "to": (NOW - timedelta(hours=1)).isoformat()})
    assert bad.status_code == 422 and bad.json()["error"] == "invalid_window"
    too_big = client.post("/api/backfill/preview", json={"from": (NOW - timedelta(days=40)).isoformat(),
                                                         "to": NOW.isoformat()})
    assert too_big.status_code == 422 and too_big.json()["error"] == "window_too_large"
    monkeypatch.setattr(settings, "backfill_max_estimated_cost_usd", 1e-9)
    over = client.post("/api/backfill/runs", json=window())
    assert over.status_code == 422 and over.json()["error"] == "over_budget" and "estimate" in over.json()
    assert client.post("/api/backfill/runs", json=window(confirm_over_budget=True)).status_code == 202


def test_status_exposes_coverage_and_backfill(env):
    client, _, _ = env
    telemetry = client.get("/api/status").json()["telemetry"]
    assert "coverage" in telemetry and "backfill" in telemetry
    assert telemetry["backfill"]["enabled"] is True
    assert client.get("/api/backfill/settings").json()["settings"]["backfill_lookback_days"] == settings.backfill_lookback_days


def test_sse_event_names_do_not_trigger_entity_toasts():
    router_substrings = ("action", "routine", "task", "contact", "commitment", "social", "topic", "briefing",
                         "pipeline", "session")
    names = ("backfill_queued", "backfill_started", "backfill_progress", "backfill_completed", "backfill_failed",
             "coverage_gap_detected")
    assert not [n for n in names if any(s in n for s in router_substrings)]


def test_ingestion_coverage_tool_reports_gaps_and_recoveries(env):
    _, store, _ = env
    day = (NOW - timedelta(days=1)).replace(hour=0, minute=0, second=0)
    store.save_coverage_interval(CoverageInterval(source="live", start=day.replace(hour=8).isoformat(),
                                                  end=day.replace(hour=13).isoformat()))
    store.save_coverage_interval(CoverageInterval(source="live", start=day.replace(hour=20).isoformat(),
                                                  end=day.replace(hour=23).isoformat()))
    data = execute_get_ingestion_coverage("yesterday", store=store, now=NOW)
    assert data["found"] and data["display_template"] == "INGESTION_COVERAGE_CARD"
    assert "from 13:00 to 20:00" in data["spoken_summary"]

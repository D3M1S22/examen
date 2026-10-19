"""Bee stream parsing and transports, with the payload shapes observed on a real account.

All values are synthetic; only the shapes follow docs/10_bee_cli_reference.md §7 (no captured data).
"""

import asyncio
import json
import sys
from datetime import datetime

import httpx
import pytest

from src.core.config import settings
from src.ingestion.stream_convo import (
    BeeClient,
    BeeProxyError,
    SseFrameParser,
    duration_ms,
    normalize_bee_time,
    parse_bee_payload,
)

RECEIVED = "2026-10-19T15:30:00"

NEW_UTTERANCE = {
    "type": "new-utterance",
    "conversation_uuid": "11111111-2222-3333-4444-555555555555",
    "utterance": {"id": 3700000001, "sample_id": "aaaa-bbbb", "start": 22.24, "end": 32.08,
                  "text": "I just unplugged the iron.", "spoken_at": "2026-10-19T13:29:34.000Z"},
}
TAGGED = {"type": "tagged-utterance", "utterance_id": 3700000001, "person_id": 42,
          "person_first_name": "Ada", "speaker_score": 0.79,
          "conversation_uuid": "11111111-2222-3333-4444-555555555555"}
CHUNKS = {"type": "new-utterance-chunks", "conversation_id": 11400000, "transcription_id": 16900000,
          "chunks": [{"id": 1, "chunk_text": "Ada talks about the iron.", "tags": ["CONVERSATION"],
                      "utterances": [3700000000, 3700000001]}]}
SUMMARY = {"type": "update-conversation-summary", "conversation_id": 11400000, "short_summary": "Household checks"}


# ---------------------------------------------------------------------------
# Pure parsing
# ---------------------------------------------------------------------------

def test_new_utterance_real_shape():
    ev = parse_bee_payload(NEW_UTTERANCE, RECEIVED)
    assert ev["event"] == "new-utterance"
    data = ev["data"]
    assert data["id"] == "3700000001"
    assert data["conversation_uuid"] == NEW_UTTERANCE["conversation_uuid"]
    assert data["speaker"] is None  # the real payload has no speaker
    assert data["received_at"] == RECEIVED
    assert data["spoken_at"] == normalize_bee_time("2026-10-19T13:29:34.000Z")
    assert data["duration_ms"] == 9840  # end − start, relative seconds


def test_tagged_utterance_and_chunks():
    tag = parse_bee_payload(TAGGED, RECEIVED)
    assert tag == {"event": "tagged-utterance", "data": {
        "utterance_id": "3700000001", "person_id": 42, "person_first_name": "Ada", "speaker_score": 0.79,
        "conversation_uuid": TAGGED["conversation_uuid"]}}
    chunks = parse_bee_payload(CHUNKS, RECEIVED)
    assert chunks["event"] == "new-utterance-chunks"
    assert chunks["data"] == {"conversation_id": 11400000, "transcription_id": 16900000,
                              "utterance_ids": ["3700000000", "3700000001"]}


def test_summary_connected_location_and_unknown():
    assert parse_bee_payload(SUMMARY, RECEIVED) == {"event": "update-conversation-summary", "data": SUMMARY}
    # `connected` has no type in `bee stream --json` output
    assert parse_bee_payload({"timestamp": 1792416597207}, RECEIVED)["event"] == "stream-connected"
    loc = parse_bee_payload({"type": "update-location", "conversation_id": 1,
                             "location": {"latitude": 45.07, "longitude": 7.68, "name": "Library"}}, RECEIVED)
    assert loc == {"event": "update-location", "data": {"latitude": 45.07, "longitude": 7.68, "name": "Library"}}
    assert parse_bee_payload({"type": "todo-created", "todo": {"id": 1}}, RECEIVED)["event"] == "stream-alive"
    # `update-utterance` does not exist on the real stream: not routed as a diarization update
    assert parse_bee_payload({"type": "update-utterance", "utterance_id": 1}, RECEIVED)["event"] == "stream-alive"


@pytest.mark.parametrize("start,end,expected", [
    (0.96, 1.6, 640), (22.24, 32.08, 9840), (None, 2.0, None), (5.0, 4.0, None), (True, 2.0, None),
])
def test_duration_ms(start, end, expected):
    assert duration_ms(start, end) == expected


def test_sse_frame_parser():
    parser = SseFrameParser()
    lines = ["retry: 4206", "", "event: connected", 'data: {"timestamp":1}', "",
             ": ping", "event: new-utterance", "data: {\"a\":", "data: 1}", ""]
    frames = [f for f in (parser.feed(line) for line in lines) if f]
    assert frames == [("event", "connected", '{"timestamp":1}'), ("ping", None, None),
                      ("event", "new-utterance", '{"a":\n1}')]


# ---------------------------------------------------------------------------
# Proxy transport (raw SSE) with a mock HTTP transport
# ---------------------------------------------------------------------------

def _sse_body(*frames: str, hang: bool = False):
    async def body():
        for frame in frames:
            yield frame.encode()
        if hang:
            await asyncio.sleep(3600)
    return body()


def _proxy_client(monkeypatch, body_factory) -> BeeClient:
    client = BeeClient(transport="proxy")

    async def fake_proxy():
        return "http://proxy.test"

    monkeypatch.setattr(client.proxy, "ensure_running", fake_proxy)
    client.http_transport_factory = lambda base: httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body_factory())
    )

    async def no_sleep(_):
        return None

    client._sleep = no_sleep
    return client


async def _collect(client: BeeClient, until: str, limit: int = 20):
    events = []
    async for ev in client.stream_events():
        events.append(ev)
        if ev["event"] == until or len(events) >= limit:
            break
    await client.aclose()
    return events


async def test_proxy_transport_frames_pings_and_payloads(monkeypatch):
    body = lambda: _sse_body(
        "retry: 4206\n\n",
        "event: connected\ndata: {\"timestamp\":1792416597207}\n\n",
        ": ping\n",
        f"event: new-utterance\ndata: {json.dumps(NEW_UTTERANCE)}\n\n",
        f"event: tagged-utterance\ndata: {json.dumps(TAGGED)}\n\n",
    )
    client = _proxy_client(monkeypatch, body)
    events = await _collect(client, until="stream-disconnected")
    names = [e["event"] for e in events]
    assert names == ["stream-connected", "stream-ping", "new-utterance", "tagged-utterance", "stream-disconnected"]
    assert events[-1]["data"]["reason"] == "eof"
    assert client.active_transport == "proxy"


async def test_proxy_transport_detects_stalled_stream(monkeypatch):
    monkeypatch.setattr(settings, "bee_stream_ping_timeout_seconds", 0.2)
    body = lambda: _sse_body("event: connected\ndata: {\"timestamp\":1}\n\n", hang=True)
    client = _proxy_client(monkeypatch, body)
    events = await _collect(client, until="stream-disconnected")
    assert [e["event"] for e in events] == ["stream-connected", "stream-disconnected"]
    assert events[-1]["data"]["reason"] == "timeout"


async def test_proxy_failures_fall_back_to_cli(monkeypatch, tmp_path):
    script = tmp_path / "fake_bee_stream.py"
    script.write_text("import json\nprint(json.dumps(%r))\n" % (NEW_UTTERANCE,))
    client = BeeClient(transport="proxy")

    async def broken_proxy():
        raise BeeProxyError("bee proxy exited")

    monkeypatch.setattr(client.proxy, "ensure_running", broken_proxy)
    monkeypatch.setattr(client, "_build_cmd", lambda args: [sys.executable, str(script)])

    async def no_sleep(_):
        return None

    client._sleep = no_sleep
    events = await _collect(client, until="new-utterance")
    assert [e["event"] for e in events].count("stream-disconnected") == 3
    assert events[-1]["event"] == "new-utterance"
    assert client.active_transport == "cli"


async def test_cli_transport_reports_alive_while_process_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "coverage_flush_seconds", 1.0)
    script = tmp_path / "silent_bee_stream.py"
    script.write_text("import time\ntime.sleep(2.5)\n")
    client = BeeClient(transport="cli")
    monkeypatch.setattr(client, "_build_cmd", lambda args: [sys.executable, str(script)])
    events = await _collect(client, until="stream-alive")
    assert events[0]["event"] == "stream-alive"  # silence is not a dead stream


# ---------------------------------------------------------------------------
# Location probe
# ---------------------------------------------------------------------------

async def test_get_location_real_shape(monkeypatch):
    client = BeeClient()

    async def fake_run_json(args, timeout=30.0):
        assert args == ["locations", "current"]
        return {"location": {"id": 7, "latitude": 45.07, "longitude": 7.68, "address": "1 Via Roma, Torino",
                             "source_device_id": None, "created_at": 1792416558579, "updated_at": 1792416558579},
                "age_ms": 1000, "is_recent": True, "recent_threshold_ms": 1800000, "timezone": "Europe/Rome"}

    monkeypatch.setattr(client, "run_json", fake_run_json)
    fix = await client.get_location()
    assert fix == {"id": 7, "latitude": 45.07, "longitude": 7.68, "address": "1 Via Roma, Torino",
                   "created_at": 1792416558579, "is_recent": True, "age_ms": 1000}


async def test_get_location_handles_cli_failure():
    # conftest replaces the Bee binary with a command that always fails
    assert await BeeClient().get_location() is None


# ---------------------------------------------------------------------------
# Semantic zones on Bee postal addresses (whole words, no substring false positives)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("address,zone", [
    ("12 Corso Carlo Alberto, Centro, Torino TO, Piemonte, 10123, Italia", "unknown"),  # not "car"
    ("3 Via Casale, Borgo Po, Torino TO, Piemonte, 10132, Italia", "unknown"),         # not "casa"
    ("Piazza della Barriera, Torino TO, Piemonte, 10154, Italia", "unknown"),          # not "bar"
    ("Stazione di Torino Porta Nuova, Torino TO, Piemonte, 10125, Italia", "transit"),
    ("Coworking Space Lounge", "work_office"),
])
def test_semantic_zone_uses_whole_words(address, zone):
    from src.core.schemas import LocationTelemetry

    assert LocationTelemetry(latitude=45.0, longitude=7.6, place_name=address).semantic_zone == zone

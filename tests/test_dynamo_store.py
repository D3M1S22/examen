"""DynamoDB-specific behaviour of the per-user store (docs/next_steps/dynamodb_storage/02, 07 §1 P1).

The shared behaviour is covered by the whole suite under ``EXAMEN_TEST_STORAGE=dynamo``; these tests
cover what only DynamoDB has: partition scoping, guards, versions, index lag, chunk moves, item size.
"""

import os
import time
import uuid
from datetime import datetime, timedelta

import pytest

from src.core.schemas import (
    BriefingReport,
    MicroEventRef,
    PlannedTask,
    SessionDossier,
    SocialCommitment,
    SocialEntity,
    UtteranceChunk,
    VerifiedAction,
)
from src.core.storage import dynamo_client, dynamo_io
from src.core.storage.dynamo_io import ItemTooLarge
from src.core.storage.dynamo_schema import key_part
from src.core.storage.dynamo_store import DynamoContextStore
from src.core.storage.sqlite_store import SQLiteContextStore
from tests import store_backend


@pytest.fixture
def moto_tables(monkeypatch):
    if store_backend.DYNAMO:  # conftest already started moto for this test
        yield
        return
    mock = store_backend.start_dynamo(monkeypatch)
    yield
    store_backend.stop_dynamo(mock)


def _uid() -> str:
    return f"usr_{uuid.uuid4().hex}"


@pytest.fixture
def store(moto_tables):
    return DynamoContextStore(user_id=_uid())


class _Recorder:
    """Proxy over the botocore client that records the partition keys of every request."""

    def __init__(self, client):
        self._client = client
        self.keys = []

    def _collect(self, payload):
        if isinstance(payload, dict):
            for name, value in payload.items():
                if name in ("pk", "g1pk", "g2pk", "g3pk") and isinstance(value, dict) and "S" in value:
                    self.keys.append(value["S"])
                elif name == "ExpressionAttributeValues":
                    continue
                else:
                    self._collect(value)
        elif isinstance(payload, list):
            for value in payload:
                self._collect(value)

    def __getattr__(self, name):
        method = getattr(self._client, name)

        def call(**kwargs):
            self._collect(kwargs)
            if name == "query":
                values = kwargs.get("ExpressionAttributeValues", {})
                cond = kwargs["KeyConditionExpression"]
                pk_placeholder = cond.split(" = ")[1].split(" ")[0]
                self.keys.append(values[pk_placeholder]["S"])
            return method(**kwargs)

        return call


def _exercise(s: DynamoContextStore) -> None:
    task = PlannedTask(title="Take out the trash", domain="routine")
    s.save_planned_task(task)
    s.save_action(VerifiedAction(action_type="trash", domain="routine", raw_statement="took out the trash",
                                 confidence=0.9))
    s.get_action_status("trash")
    s.list_recent_actions()
    s.save_social_contact(SocialEntity(person_name="Ada Lovelace", company_or_role="Engines",
                                       commitments=["send the notes"]))
    s.search_social_contact("ada")
    s.save_topic_briefing(BriefingReport(topic_title="Raft", context_type="lecture", session_id="ev-1"))
    s.get_topic_briefing("raft")
    s.list_topic_briefings(session_id="ev-1")
    dossier = SessionDossier(session_id="ev-1", start_time=datetime.now().isoformat(),
                             last_updated_at=datetime.now().isoformat(), status="active")
    s.save_session_dossier(dossier)
    s.append_session_chunk(UtteranceChunk(chunk_id="c1", text="hello", timestamp="2026-10-21T10:00:00"), "ev-1")
    s.assign_chunks(["c1"], "ev-2", None)
    s.get_session_dossier()
    s.get_open_event()
    s.list_events_pending_final()
    s.record_ingested_utterance({"source_key": "live:x:c1", "ts": "2026-10-21T10:00:00", "text_hash": "h"})
    s.list_ledger_entries("2026-10-21", "2026-10-22")
    s.purge_ingest_ledger("2026-10-20")
    s.map_bee_conversation("conv-uuid", 42)
    s.record_latency("pipeline", 12.5)
    s.get_latency_metrics()
    s.export_all()
    s.delete_all_data()


def test_every_request_targets_the_tenant_partition(moto_tables):
    uid = _uid()
    recorder = _Recorder(dynamo_client.service_client())
    s = DynamoContextStore(user_id=uid, client_getter=lambda: recorder)
    _exercise(s)
    assert recorder.keys, "no request recorded"
    stray = [k for k in recorder.keys if k != uid and not k.startswith(f"{uid}#")]
    assert stray == []


def test_partitions_are_isolated(moto_tables):
    a, b = DynamoContextStore(user_id=_uid()), DynamoContextStore(user_id=_uid())
    a.save_planned_task(PlannedTask(title="Water the plants", domain="routine"))
    a.save_social_contact(SocialEntity(person_name="Grace Hopper"))
    assert b.list_planned_tasks() == [] and b.get_social_contact("Grace Hopper") is None
    b.save_planned_task(PlannedTask(title="Feed the cat", domain="routine"))
    a.delete_all_data()
    assert a.export_all() == {}
    assert [t.title for t in b.list_planned_tasks()] == ["Feed the cat"]


def test_contact_name_guard_keeps_one_contact(store):
    first = store.save_social_contact(SocialEntity(person_name="Marco Rossi", company_or_role="ACME"))
    second = store.save_social_contact(SocialEntity(person_name="  marco rossi ", company_or_role="ACME Corp"))
    assert first == second
    assert len(store.export_all()["social_contacts"]) == 1
    # Renaming moves the guard
    contact = store.get_social_contact(first)
    contact.person_name = "Marco Bianchi"
    store.save_social_contact(contact)
    assert store.get_social_contact("Marco Bianchi").id == first
    assert store.get_social_contact("Marco Rossi") is None


def test_concurrent_commitment_creation_adopts_the_winner(store, monkeypatch):
    winner = store.save_social_commitment(SocialCommitment(contact_name="Ada", debtor="user",
                                                           description="send the slides"))
    real_get = store._get
    calls = {"n": 0}

    def stale_get(sk):  # the first guard read happens "before" the winner's write
        if sk.startswith("COMMITKEY#") and calls["n"] == 0:
            calls["n"] += 1
            return None
        return real_get(sk)

    monkeypatch.setattr(store, "_get", stale_get)
    loser = store.save_social_commitment(SocialCommitment(contact_name="ada", debtor="user",
                                                          description="Send the slides"))
    assert loser == winner
    commitments = store.list_social_commitments(contact_name="Ada")
    assert len(commitments) == 1
    tasks = store.list_planned_tasks(origin="social_commitment")
    assert len(tasks) == 1 and commitments[0].auto_scheduled_task_id == tasks[0].id


def test_dossier_save_keeps_links_written_concurrently(moto_tables):
    uid = _uid()
    engine_side, pipeline_side = DynamoContextStore(user_id=uid), DynamoContextStore(user_id=uid)
    now = datetime.now().isoformat()
    dossier = SessionDossier(session_id="ev-1", start_time=now, last_updated_at=now, status="active")
    engine_side.save_session_dossier(dossier)
    assert dossier._store_version == 1
    pipeline_side.link_micro_event_to_session("ev-1", MicroEventRef(event_type="action", record_id="a1",
                                                                     timestamp=now, headline="x"))
    dossier.title = "Renamed by the engine"
    engine_side.save_session_dossier(dossier)  # stale version: conflict, merge, retry
    stored = pipeline_side.get_session_dossier("ev-1")
    assert stored.title == "Renamed by the engine"
    assert [(e.event_type, e.record_id) for e in stored.linked_micro_events] == [("action", "a1")]
    assert stored._store_version == 3


def test_open_event_lookup_confirms_index_candidates(store, monkeypatch):
    now = datetime.now().isoformat()
    from src.core.schemas import SessionSegment

    ev = SessionDossier(session_id="ev-open", start_time=now, last_updated_at=now, status="active",
                        segments=[SessionSegment(segment_id="s1", index=1, start_time=now)])
    store.save_session_dossier(ev)
    assert store.get_open_event().session_id == "ev-open"
    ev.status = "concluded"
    ev.final_status = "pending"
    store.save_session_dossier(ev)
    # A lagging index still lists the event as open: the consistent read rejects it
    stale = {"pk": store.user_id, "sk": "DOSSIER#ev-open", "ingest_source": "live"}
    real_index = store._index
    monkeypatch.setattr(store, "_index", lambda index, gpk, **kw: (
        iter([stale]) if gpk.endswith("#DSTATE#open") else real_index(index, gpk, **kw)))
    assert store.get_open_event() is None
    assert [e.session_id for e in store.list_events_pending_final()] == ["ev-open"]


def test_listings_tolerate_index_lag(store, monkeypatch):
    store.save_action(VerifiedAction(id="a-old", action_type="gas", domain="safety", raw_statement="gas off",
                                     confidence=0.9, timestamp="2026-10-20T08:00:00"))
    store.save_action(VerifiedAction(id="a-new", action_type="gas", domain="safety", raw_statement="gas off",
                                     confidence=0.9, timestamp="2026-10-21T08:00:00"))
    monkeypatch.setattr(dynamo_io, "INDEX_FILTER", lambda index, item: item.get("id") != "a-new")
    assert [a.id for a in store.list_recent_actions()] == ["a-old"]
    # A lookup by id never depends on the index
    assert store.get_action_status("a-new").id == "a-new"


def test_assign_chunks_moves_in_batches_and_keeps_order(store):
    for i in range(70):
        store.append_session_chunk(UtteranceChunk(chunk_id=f"c{i}", text=f"t{i}",
                                                  timestamp=f"2026-10-21T10:{i // 60:02d}:{i % 60:02d}"), "ev-a")
    store.append_session_chunk(UtteranceChunk(chunk_id="same-ts", text="first", timestamp="2026-10-21T11:00:00"), "ev-a")
    store.append_session_chunk(UtteranceChunk(chunk_id="same-ts-2", text="second", timestamp="2026-10-21T11:00:00"), "ev-a")
    ids = [f"c{i}" for i in range(70)] + ["same-ts", "same-ts-2"]
    store.assign_chunks(ids, "ev-b", "seg-1", on_topic=True)
    store.assign_chunks(ids, "ev-b", "seg-1", on_topic=True)  # idempotent
    moved = store.list_session_chunks("ev-b")
    assert [c.chunk_id for c in moved] == ids
    assert store.list_session_chunks("ev-a") == []
    assert set(store.get_chunk_segments("ev-b").values()) == {"seg-1"}
    # Re-appending a chunk keeps one copy
    store.append_session_chunk(UtteranceChunk(chunk_id="c0", text="t0", timestamp="2026-10-21T10:00:00"), "ev-b",
                               segment_id="seg-1")
    assert len(store.list_session_chunks("ev-b")) == 72


def test_large_items_are_compressed_and_round_trip(store):
    markdown = ("The Raft leader election works by randomized timeouts. " * 10000)[:550_000]
    store.save_topic_briefing(BriefingReport(id="big", topic_title="Raft", context_type="lecture",
                                             deep_dive_markdown=markdown))
    assert store.get_topic_briefing("big").deep_dive_markdown == markdown
    noise = os.urandom(700_000).hex()
    with pytest.raises(ItemTooLarge) as err:
        store.save_topic_briefing(BriefingReport(id="huge", topic_title="Noise", context_type="lecture",
                                                 deep_dive_markdown=noise))
    assert noise[:20] not in str(err.value)


def _raw(store, sk):
    return store.table.client.get_item(TableName=store.table.name, Key=dynamo_io.encode(store._key(sk)))["Item"]


def test_link_on_a_compressed_dossier_is_kept(store):
    now = datetime.now().isoformat()
    refs = [MicroEventRef(event_type="action", record_id=f"a{i}", timestamp=now, headline=f"{i} " + "x" * 250)
            for i in range(1500)]
    dossier = SessionDossier(session_id="ev-big", start_time=now, last_updated_at=now, status="active",
                             linked_micro_events=refs)
    store.save_session_dossier(dossier)
    assert "linked_micro_events_json__z" in _raw(store, "DOSSIER#ev-big")

    store.link_micro_event_to_session("ev-big", MicroEventRef(event_type="action", record_id="new", timestamp=now,
                                                              headline="late link"))
    assert "linked_micro_events_json__z" in _raw(store, "DOSSIER#ev-big")  # still compressed, size-checked
    stored = store.get_session_dossier("ev-big")
    assert stored.linked_micro_events[-1].record_id == "new" and len(stored.linked_micro_events) == 1501

    stored.title = "Saved by the engine"
    store.save_session_dossier(stored)
    assert store.get_session_dossier("ev-big").linked_micro_events[-1].record_id == "new"


def test_partial_update_drops_the_stale_compressed_copy(store):
    big = ("Raft log replication. " * 30000)[:400_000]
    store.table.put({"pk": store.user_id, "sk": "T#1", "notes_json": big})
    assert "notes_json__z" in _raw(store, "T#1")
    store.table.update(store._key("T#1"), set_={"notes_json": "small"})
    assert "notes_json__z" not in _raw(store, "T#1")
    assert store.table.get(store._key("T#1"))["notes_json"] == "small"


def test_key_part_strips_separators():
    assert key_part("ev-1") == "ev-1"
    assert "#" not in key_part("a#b") and key_part("a#b").startswith("h_")
    assert len(key_part("x" * 500)) < 64


def test_search_cache_expiry(store):
    store.put_cached_search("raft", "fake", [{"title": "t"}])
    assert store.get_cached_search("raft", 3600) is not None
    old = (datetime.now() - timedelta(hours=2)).isoformat()
    store.table.update(store._key(store._cache_sk("raft")), set_={"fetched_at": old})
    assert store.get_cached_search("raft", 3600) is None


def test_legacy_finalizing_status_reads_as_paused(store):
    store.append_chunk_to_session("legacy-2", "chunk")
    store.table.update(store._key("DOSSIER#legacy-2"), set_={"status": "finalizing"})
    assert store.get_session_dossier("legacy-2").status == "paused"


def test_export_matches_sqlite_shape(store, tmp_path):
    sqlite = SQLiteContextStore(str(tmp_path / "parity.db"))
    for s in (sqlite, store):
        s.save_planned_task(PlannedTask(id="t1", title="Call Dr. Smith", domain="personal",
                                        created_at="2026-10-21T09:00:00", confidence=0.5))
        s.save_action(VerifiedAction(id="a1", action_type="Iron", domain="safety", raw_statement="iron unplugged",
                                     confidence=1.0, timestamp="2026-10-21T08:00:00", matched_task_id=None))
        s.record_ingested_utterance({"source_key": "k1", "ts": "2026-10-21T08:00:00", "text_hash": "h",
                                     "received_at": "2026-10-21T08:00:01", "categories": ["action"],
                                     "duration_ms": 1200})
        s.map_bee_conversation("u1", 7)
    a, b = sqlite.export_all(), store.export_all()
    for table in ("planned_tasks", "verified_actions", "ingest_ledger", "bee_conversation_map"):
        rows_a = [{k: v for k, v in r.items() if k != "first_seen_at"} for r in a[table]]
        rows_b = [{k: v for k, v in r.items() if k != "first_seen_at"} for r in b[table]]
        assert rows_a == rows_b, table
    assert set(b) <= set(a)


def test_tenant_credentials_are_cached_and_refreshed(monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "dynamo_tenant_role_arn", "arn:aws:iam::123456789012:role/examen-tenant-data")
    dynamo_client.reset_clients()
    issued = []

    def fake_assume(user_id):
        issued.append(user_id)
        return object(), time.time() + (100 if len(issued) == 1 else 3600)

    monkeypatch.setattr(dynamo_client, "_assume", fake_assume)
    first = dynamo_client.tenant_client("usr_a")
    second = dynamo_client.tenant_client("usr_a")  # 100 s left: inside the refresh margin
    third = dynamo_client.tenant_client("usr_a")
    dynamo_client.tenant_client("usr_b")
    assert issued == ["usr_a", "usr_a", "usr_b"]
    assert first is not second and second is third
    dynamo_client.reset_clients()

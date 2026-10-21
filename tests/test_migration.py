"""SQLite → DynamoDB migration (docs/next_steps/dynamodb_storage/06, 07 P4)."""

import uuid
from datetime import datetime

import pytest

from src.core.auth.dynamo_store import DynamoAuthStore
from src.core.auth.store import AuthStore, BeeLink
from src.core.ops_dynamo_store import DynamoOpsStore
from src.core.ops_store import OpsStore
from src.core.schemas import (
    BackfillRun,
    BriefingReport,
    CoverageInterval,
    MicroEventRef,
    PlannedTask,
    SessionDossier,
    SessionSegment,
    SocialCommitment,
    SocialEntity,
    UtteranceChunk,
    VerifiedAction,
)
from src.core.storage import migration
from src.core.storage.dynamo_store import DynamoContextStore
from src.core.storage.sqlite_store import SQLiteContextStore
from tests import store_backend

PASSWORD = "Correct horse battery 9"


@pytest.fixture
def moto_tables(monkeypatch):
    if store_backend.DYNAMO:
        yield
        return
    mock = store_backend.start_dynamo(monkeypatch)
    yield
    store_backend.stop_dynamo(mock)


def _populate(s: SQLiteContextStore) -> None:
    now = datetime.now().isoformat()
    s.save_planned_task(PlannedTask(id="t1", title="Water the plants", domain="routine", created_at=now))
    s.save_action(VerifiedAction(id="a1", action_type="gas", domain="safety", raw_statement="gas is off",
                                 confidence=0.8, timestamp=now))
    s.save_social_contact(SocialEntity(person_name="Ada Lovelace", company_or_role="Engines",
                                       commitments=["send the notes"]))
    s.save_social_commitment(SocialCommitment(contact_name="Ada Lovelace", debtor="contact", description="call back"))
    s.save_topic_briefing(BriefingReport(id="b1", topic_title="Raft", context_type="lecture", session_id="ev-1",
                                         kind="segment"))
    seg = SessionSegment(segment_id="s1", index=1, start_time=now)
    s.save_session_dossier(SessionDossier(session_id="ev-1", start_time=now, last_updated_at=now, status="active",
                                          segments=[seg]))
    s.link_micro_event_to_session("ev-1", MicroEventRef(event_type="action", record_id="a1", headline="gas"))
    for i, (cid, ts) in enumerate([("c1", "2026-10-21T10:00:00"), ("c2", "2026-10-21T10:00:00"),
                                   ("c3", "2026-10-21T09:00:00")]):
        s.append_session_chunk(UtteranceChunk(chunk_id=cid, text=f"text {i}", timestamp=ts), "ev-1", segment_id="s1")
    s.patch_utterance_speaker("c1", "spk-1", "user")
    s.put_cached_search("raft", "fake", [{"title": "t"}])
    s.save_coverage_interval(CoverageInterval(id="cov1", source="live", start=now, end=now))
    s.record_ingested_utterance({"source_key": "live:x:c1", "ts": "2026-10-21T10:00:00", "text_hash": "h1",
                                 "received_at": "2026-10-21T10:00:02", "categories": ["action"]})
    s.map_bee_conversation("conv-1", 99)
    s.save_backfill_run(BackfillRun(id="run1", trigger="manual", window_from=now, window_to=now))
    s.record_latency("pipeline", 42.0)


def test_user_migration_round_trips_and_is_idempotent(moto_tables, tmp_path):
    source = SQLiteContextStore(str(tmp_path / "examen.db"))
    _populate(source)
    uid = f"usr_{uuid.uuid4().hex}"
    report = migration.migrate_user(uid, source.db_path)
    assert report["ok"], report
    assert migration.migrate_user(uid, source.db_path)["stored"] == report["stored"]  # second run: no-op

    target = DynamoContextStore(user_id=uid)
    a, b = source.export_all(), target.export_all()
    for table, rows in a.items():
        if not rows:
            continue
        if table == "system_telemetry":
            assert [r["latency_ms"] for r in b[table]] == [r["latency_ms"] for r in rows]
            continue
        key = lambda r: tuple(str(v) for v in r.values())  # noqa: E731
        assert sorted(b.get(table, []), key=key) == sorted(rows, key=key), table

    # The index, guard and pointer items work: reads behave like the source store
    assert [t.id for t in target.list_planned_tasks()] == [t.id for t in source.list_planned_tasks()]
    assert target.get_social_contact("ada lovelace").id == source.get_social_contact("Ada Lovelace").id
    assert target.get_open_event().session_id == "ev-1"
    assert [c.chunk_id for c in target.list_session_chunks("ev-1")] == ["c3", "c1", "c2"]
    assert [x.chunk_id for x in target.list_session_chunks("ev-1")] == \
        [x.chunk_id for x in source.list_session_chunks("ev-1")]
    assert [b.id for b in target.list_topic_briefings(session_id="ev-1")] == ["b1"]
    assert target.get_bee_conversation_uuid(99) == "conv-1"
    assert [e["source_key"] for e in target.list_ledger_entries("2026-10-21", "2026-10-22")] == ["live:x:c1"]
    assert target.get_action_status("gas").id == "a1"
    assert target.get_cached_search("raft", 3600)["provider"] == "fake"
    assert target.get_session_dossier("ev-1").linked_micro_events[0].record_id == "a1"
    # Writes after migration keep working (versions, guards)
    target.append_session_chunk(UtteranceChunk(chunk_id="c4", text="later", timestamp="2026-10-21T11:00:00"), "ev-1")
    assert target.save_social_contact(SocialEntity(person_name="ADA LOVELACE")) == source.get_social_contact("Ada Lovelace").id


def test_auth_and_ops_migration(moto_tables, tmp_path):
    auth = AuthStore(str(tmp_path / "auth.db"))
    user = auth.create_user("ada@example.com", PASSWORD)
    auth.create_session(user.id)
    auth.create_api_token(user.id, "Alexa")
    auth.save_bee_link(BeeLink(user_id=user.id, bee_user_id=5, state="linked"))
    auth.audit("login", user_id=user.id)
    counts = migration.migrate_auth(auth.db_path)
    assert counts == {"users": 1, "sessions": 1, "api_tokens": 1, "bee_links": 1, "audit_log": 1}
    target = DynamoAuthStore()
    assert target.authenticate("ada@example.com", PASSWORD).id == user.id
    assert target.find_bee_link(5).user_id == user.id
    assert [t.name for t in target.list_api_tokens(user.id)] == ["Alexa"]
    assert [e["event"] for e in target.list_audit(user_id=user.id)] == ["login"]

    ops = OpsStore(str(tmp_path / "ops.db"))
    ops.insert_events([{"ref": "r1", "at": datetime.now().astimezone().isoformat(), "level": "warning", "code": "x",
                        "component": "c", "message": "m", "fingerprint": "f", "user_id": user.id}])
    ops.save_change_set({"backfill_lookback_days": 3}, {}, user.id)
    ops.add_token_usage([{"hour": "2026-10-21T10:00:00+00:00", "provider": "bedrock", "model_id": "m",
                          "role": "gatekeeper", "user_id": user.id, "calls": 2, "input_tokens": 30}])
    counts = migration.migrate_ops(ops.db_path)
    assert counts["service_events"] == 1 and counts["settings_history"] == 1 and counts["token_usage"] == 1
    dyn = DynamoOpsStore()
    assert dyn.list_overrides()["backfill_lookback_days"]["value"] == 3 and dyn.settings_version() == 1
    assert [e["id"] for e in dyn.list_events()] == [1] and dyn.count_events() == 1
    dyn.insert_events([{"ref": "r2", "at": datetime.now().astimezone().isoformat(), "level": "info", "code": "x",
                        "component": "c", "message": "m2", "fingerprint": "f"}])
    assert [e["id"] for e in dyn.list_events()] == [2, 1]  # the counter continues after the migrated ids
    assert dyn.token_usage_summary("2026-10-21T00:00:00+00:00")["totals"]["input_tokens"] == 30
    assert dyn.list_history()[0]["changes"][0]["key"] == "backfill_lookback_days"

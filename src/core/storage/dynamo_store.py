"""DynamoDB implementation of the per-user context store (docs/next_steps/dynamodb_storage/02).

One instance per tenant. Every item lives in the partition ``pk = <user_id>``; every index partition
key starts with ``<user_id>#``. With IAM tenant isolation on, the client can touch nothing else.

Consistency rule (02 §4): base-table reads are strongly consistent and back every read-modify-write;
index reads only list or find candidates, which are then confirmed with a consistent read.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from src.core.schemas import (
    BackfillRun,
    BriefingReport,
    CoverageInterval,
    MicroEventRef,
    PlannedTask,
    SessionDossier,
    SocialCommitment,
    SocialEntity,
    SocialWebProfile,
    SpeakerAttribution,
    UtteranceChunk,
    VerifiedAction,
)
from src.core.storage import rules
from src.core.storage.base import AbstractContextStore
from src.core.storage.dynamo_io import DynamoTable, Expr, is_conditional_failure, pack
from src.core.storage.dynamo_schema import INDEX, USER, key_part, table_name
from src.core.time_utils import historical_action_may_resolve

logger = logging.getLogger("examen.storage.dynamo")

LEGACY_PARTITION = "_local"
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_HIGH = "￿"
_MAX_RETRIES = 5

# SQLite columns per table (the attribute names of the items, and the export format)
COLUMNS: Dict[str, Tuple[str, ...]] = {
    "planned_tasks": ("id", "title", "domain", "scheduled_time", "recurrence", "status", "completed_at",
                      "verified_action_id", "created_at", "origin", "raw_statement", "confidence",
                      "relative_time_anchor", "session_id", "location_json", "ingest_source", "ingest_run_id",
                      "source_key", "recovered", "speaker_json"),
    "verified_actions": ("id", "action_type", "domain", "raw_statement", "confidence", "timestamp", "is_revoked",
                         "matched_task_id", "location_json", "session_id", "ingest_source", "ingest_run_id",
                         "source_key", "speaker_json"),
    "social_contacts": ("id", "person_name", "company_or_role", "contact_info", "commitments_json",
                        "key_topics_json", "timestamp", "web_profile_json", "location_encountered", "session_id",
                        "website_url"),
    "social_commitments": ("id", "contact_name", "debtor", "description", "due_date_raw", "normalized_deadline",
                           "status", "auto_scheduled_task_id", "created_at"),
    "topic_briefings": ("id", "topic_title", "context_type", "executive_summary_json", "explanatory_synthesis",
                        "deep_dive_markdown", "web_sources_json", "action_items_json", "created_at", "session_id",
                        "segment_id", "kind"),
    "utterance_diarization": ("chunk_id", "speaker_id", "speaker_role", "updated_at"),
    "session_dossiers": ("session_id", "title", "domain", "start_time", "last_updated_at", "concluded_at", "status",
                         "location_json", "transcript_chunks_json", "key_discussion_points_json",
                         "linked_micro_events_json", "final_briefing_id", "created_at", "conversation_uuids_json",
                         "segments_json", "anchor_location_json", "last_on_topic_at", "paused_at",
                         "hard_close_deadline", "final_status", "final_revision", "transitions_json",
                         "research_ledger_json", "topic_profile_json", "pending_chunk_ids_json", "ingest_source",
                         "ingest_run_id"),
    "session_chunks": ("chunk_id", "session_id", "segment_id", "conversation_uuid", "ts", "text", "word_count",
                       "speaker_id", "speaker_role", "categories_json", "on_topic", "location_json"),
    "web_search_cache": ("query_norm", "provider", "results_json", "fetched_at"),
    "ingest_coverage": ("id", "source", "start_ts", "end_ts", "is_open", "degraded", "run_id", "utterances", "errors"),
    "ingest_ledger": rules.LEDGER_COLUMNS,
    "bee_conversation_map": ("uuid", "id", "first_seen_at"),
    "backfill_runs": ("id", "trigger", "window_from", "window_to", "status", "payload_json", "created_at"),
    "system_telemetry": ("id", "timestamp", "event_type", "latency_ms", "model_id", "details_json"),
}

# sk prefix → SQLite table (export); guard and pointer items are not data
PREFIX_TABLE = {
    "TASK": "planned_tasks", "ACTION": "verified_actions", "CONTACT": "social_contacts",
    "COMMIT": "social_commitments", "BRIEF": "topic_briefings", "DIAR": "utterance_diarization",
    "DOSSIER": "session_dossiers", "CHUNK": "session_chunks", "CACHE": "web_search_cache",
    "COV": "ingest_coverage", "LEDGER": "ingest_ledger", "BEECONV": "bee_conversation_map",
    "RUN": "backfill_runs", "TEL": "system_telemetry",
}
HISTORY_PREFIXES = ("COV#", "LEDGER#", "BEECONV#", "BEECONVID#", "RUN#")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _epoch_after(days: float) -> int:
    return int(time.time() + days * 86400)


def dossier_state(cols: Dict[str, Any]) -> str:
    status = cols.get("status")
    if status in ("active", "paused") and cols.get("segments_json"):
        return "open"
    if status == "concluded" and cols.get("final_status") in ("pending", "synthesizing"):
        return "pending_final"
    return "closed"


def _ascii_lower(value: Optional[str]) -> str:
    return rules.ascii_lower(value or "")


class DynamoContextStore(AbstractContextStore):
    """Per-user store in the ``examen-user`` table (one partition per user)."""

    def __init__(self, user_id: Optional[str] = None, client_getter: Optional[Callable[[], Any]] = None,
                 table: Optional[str] = None):
        from src.core.storage import dynamo_client

        self.user_id = user_id or LEGACY_PARTITION
        getter = client_getter or (
            (lambda: dynamo_client.tenant_client(self.user_id)) if user_id else dynamo_client.service_client
        )
        self.table = DynamoTable(getter, table or table_name(USER))
        self._g1, self._g2, self._g3 = INDEX[USER]["g1"], INDEX[USER]["g2"], INDEX[USER]["g3"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _key(self, sk: str) -> Dict[str, str]:
        return {"pk": self.user_id, "sk": sk}

    def _gpk(self, suffix: str) -> str:
        return f"{self.user_id}#{suffix}"

    def _item(self, sk: str, row: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
        return {"pk": self.user_id, "sk": sk, **row, **{k: v for k, v in extra.items() if v is not None}}

    def _get(self, sk: str) -> Optional[Dict[str, Any]]:
        return self.table.get(self._key(sk))

    def _prefix(self, prefix: str, forward: bool = True, attributes: Optional[List[str]] = None,
                limit: Optional[int] = None) -> Iterable[Dict[str, Any]]:
        return self.table.query("pk", self.user_id, sk_attr="sk", begins_with=prefix, forward=forward,
                                attributes=attributes, page_size=limit)

    def _index(self, index: str, gpk: str, forward: bool = True, **kwargs: Any) -> Iterable[Dict[str, Any]]:
        n = index[-1] if index[-1].isdigit() else {"timeline": "1", "timeline_keys": "2", "group_keys": "3"}[index]
        return self.table.query(f"g{n}pk", gpk, index=index, sk_attr=f"g{n}sk", forward=forward, **kwargs)

    def _full(self, keys: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self.table.batch_get([self._key(k["sk"]) for k in keys])

    def _delete_keys(self, sks: Iterable[str]) -> int:
        return self.table.batch_write(deletes=[self._key(sk) for sk in sks])

    # ------------------------------------------------------------------
    # Planned tasks
    # ------------------------------------------------------------------
    def save_planned_task(self, task: PlannedTask) -> str:
        rec_id = task.id or str(uuid.uuid4())
        task.id = rec_id
        row = {
            "id": rec_id, "title": task.title.strip(), "domain": task.domain, "scheduled_time": task.scheduled_time,
            "recurrence": task.recurrence, "status": task.status, "completed_at": task.completed_at,
            "verified_action_id": task.verified_action_id, "created_at": task.created_at, "origin": task.origin,
            "raw_statement": task.raw_statement, "confidence": task.confidence,
            "relative_time_anchor": task.relative_time_anchor, "session_id": task.session_id,
            "location_json": json.dumps(task.location) if task.location else None,
            "ingest_source": task.ingest_source, "ingest_run_id": task.ingest_run_id,
            "source_key": task.source_key, "recovered": 1 if task.recovered else 0,
            "speaker_json": rules.speaker_to_json(task.speaker),
        }
        self.table.put(self._item(f"TASK#{rec_id}", row), what="planned task")
        return rec_id

    def get_planned_task(self, task_id: str) -> Optional[PlannedTask]:
        item = self._get(f"TASK#{task_id}")
        return rules.row_to_planned_task(item) if item else None

    def list_planned_tasks(
        self,
        status: Optional[str] = None,
        domain: Optional[str] = None,
        origin: Optional[str] = None,
        ingest_source: Optional[str] = None,
    ) -> List[PlannedTask]:
        rows = [
            r for r in self._prefix("TASK#")
            if (not ingest_source or r.get("ingest_source") == ingest_source)
            and (not status or r.get("status") == status)
            and (not domain or r.get("domain") == domain)
            and (not origin or r.get("origin") == origin)
        ]
        # SQLite: ORDER BY scheduled_time ASC (NULL first), created_at ASC
        rows.sort(key=lambda r: (r.get("scheduled_time") is not None, r.get("scheduled_time") or "",
                                 r.get("created_at") or ""))
        return [rules.row_to_planned_task(r) for r in rows]

    def _update_existing(self, sk: str, set_: Dict[str, Any], remove: Iterable[str] = ()) -> bool:
        try:
            self.table.update(self._key(sk), set_=set_, remove=remove, condition="attribute_exists(sk)")
            return True
        except Exception as e:
            if is_conditional_failure(e):
                return False
            raise

    def complete_planned_task(
        self, task_id: str, verified_action_id: str, completed_at: Optional[str] = None
    ) -> bool:
        return self._update_existing(f"TASK#{task_id}", {
            "status": "completed", "completed_at": completed_at or _now_iso(), "verified_action_id": verified_action_id,
        })

    def update_planned_task(self, task: PlannedTask) -> bool:
        if not task.id:
            return False
        return self._update_existing(f"TASK#{task.id}", {
            "title": task.title.strip(), "domain": task.domain, "scheduled_time": task.scheduled_time,
            "recurrence": task.recurrence, "status": task.status, "completed_at": task.completed_at,
            "verified_action_id": task.verified_action_id, "origin": task.origin,
            "raw_statement": task.raw_statement, "confidence": task.confidence,
            "relative_time_anchor": task.relative_time_anchor, "session_id": task.session_id,
            "location_json": json.dumps(task.location) if task.location else None,
            "speaker_json": rules.speaker_to_json(task.speaker),
        })

    def delete_planned_task(self, task_id: str) -> bool:
        return self.table.delete(self._key(f"TASK#{task_id}"), return_old=True) is not None

    def match_and_resolve_task(self, action: VerifiedAction) -> Optional[PlannedTask]:
        pending_tasks = self.list_planned_tasks(status="pending")
        historical = action.ingest_source == "backfill"
        if historical:
            pending_tasks = [
                t for t in pending_tasks
                if historical_action_may_resolve(action.timestamp, t.created_at, t.recurrence)
            ]
        if not pending_tasks:
            return None

        action_text = rules.action_text(action)
        for task in pending_tasks:
            if rules.action_matches_task(action_text, task):
                self.complete_planned_task(task_id=task.id, verified_action_id=action.id,
                                           completed_at=action.timestamp)
                task.status = "completed"
                task.completed_at = action.timestamp
                task.verified_action_id = action.id
                # Closed-loop reconciliation: fulfil the commitment that scheduled this task
                if task.origin == "social_commitment":
                    for row in self._prefix("COMMIT#"):
                        if row.get("auto_scheduled_task_id") == task.id:
                            self._update_existing(row["sk"], {"status": "fulfilled"})
                return task

        open_commitments = self.list_social_commitments(debtor="user", status="open")
        if historical:
            open_commitments = [
                c for c in open_commitments if historical_action_may_resolve(action.timestamp, c.created_at)
            ]
        for com in open_commitments:
            if rules.action_matches_commitment(action_text, com):
                self.update_social_commitment_status(com.id, "fulfilled")
        return None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def save_action(self, action: VerifiedAction) -> str:
        rec_id = action.id or str(uuid.uuid4())
        action.id = rec_id
        if not action.matched_task_id:
            resolved_task = self.match_and_resolve_task(action)
            if resolved_task:
                action.matched_task_id = resolved_task.id
        else:
            self.complete_planned_task(task_id=action.matched_task_id, verified_action_id=rec_id,
                                       completed_at=action.timestamp)
        row = {
            "id": rec_id, "action_type": action.action_type.lower(), "domain": action.domain,
            "raw_statement": action.raw_statement, "confidence": action.confidence, "timestamp": action.timestamp,
            "is_revoked": 1 if action.is_revoked else 0, "matched_task_id": action.matched_task_id,
            "location_json": json.dumps(action.location) if action.location else None,
            "session_id": action.session_id, "ingest_source": action.ingest_source,
            "ingest_run_id": action.ingest_run_id, "source_key": action.source_key,
            "speaker_json": rules.speaker_to_json(action.speaker),
        }
        self.table.put(self._item(f"ACTION#{rec_id}", row, g1pk=self._gpk("ACTION"),
                                  g1sk=f"{action.timestamp}#{rec_id}"), what="action")
        return rec_id

    def get_verified_action(self, action_id: str) -> Optional[VerifiedAction]:
        item = self._get(f"ACTION#{action_id}")
        return rules.row_to_action(item) if item else None

    def set_action_speaker(self, action_id: str, speaker: SpeakerAttribution, revoke: bool = False) -> bool:
        set_: Dict[str, Any] = {"speaker_json": rules.speaker_to_json(speaker)}
        if revoke:
            set_["is_revoked"] = 1
        return self._update_existing(f"ACTION#{action_id}", set_)

    def get_action_status(
        self, action_query: str, target_date: Optional[str] = None
    ) -> Optional[VerifiedAction]:
        target = action_query.strip()
        pattern = f"%{target.lower()}%"
        date_pattern = f"{target_date}%" if target_date else None

        def eligible(row: Dict[str, Any]) -> bool:
            return not row.get("is_revoked") and (date_pattern is None or rules.sql_like(row.get("timestamp"), date_pattern))

        candidates = []
        by_id = self._get(f"ACTION#{target}") if target else None
        if by_id and eligible(by_id):
            candidates.append(by_id)
        e = Expr()
        for row in self._index(self._g1, self._gpk("ACTION"), forward=False,
                               begins_with=target_date if target_date else None,
                               filter_expr=f"{e.name('is_revoked')} = {e.value(0)}", expr=e):
            if eligible(row) and (rules.sql_like(row.get("action_type"), pattern)
                                  or rules.sql_like(row.get("raw_statement"), pattern)):
                candidates.append(row)
                break
        if not candidates:
            return None
        return rules.row_to_action(max(candidates, key=lambda r: r.get("timestamp") or ""))

    def list_recent_actions(
        self, limit: int = 10, domain: Optional[str] = None, ingest_source: Optional[str] = None
    ) -> List[VerifiedAction]:
        e = Expr()
        clauses = [f"{e.name('is_revoked')} = {e.value(0)}"]
        if domain and domain != "all":
            clauses.append(f"{e.name('domain')} = {e.value(domain)}")
        if ingest_source:
            clauses.append(f"{e.name('ingest_source')} = {e.value(ingest_source)}")
        out: List[VerifiedAction] = []
        if limit <= 0:
            return out
        for row in self._index(self._g1, self._gpk("ACTION"), forward=False,
                               filter_expr=" AND ".join(clauses), expr=e):
            out.append(rules.row_to_action(row))
            if len(out) >= limit:
                break
        return out

    # ------------------------------------------------------------------
    # Social recall
    # ------------------------------------------------------------------
    def _contact_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        guard = self._get(f"CONTACTNAME#{rules.contact_name_key(name)}")
        return self._get(f"CONTACT#{guard['contact_id']}") if guard else None

    def save_social_contact(self, contact: SocialEntity) -> str:
        rec_id = contact.id
        if not rec_id and contact.person_name:
            existing = self._contact_by_name(contact.person_name)
            if existing:
                rec_id = existing["id"]
        if not rec_id:
            rec_id = str(uuid.uuid4())
        contact.id = rec_id

        structured_commitments = contact.get_commitments_as_objects()
        unique_commitments: List[SocialCommitment] = []
        seen_keys = set()
        for com in structured_commitments:
            key = (com.description.strip().lower(), com.debtor)
            if key not in seen_keys:
                seen_keys.add(key)
                if not com.contact_name:
                    com.contact_name = contact.person_name
                com.id = self.save_social_commitment(com)
                unique_commitments.append(com)
        commitments_payload = [c.model_dump() if hasattr(c, "model_dump") else c for c in unique_commitments]

        web_profile_str = None
        website_url_val = getattr(contact, "website_url", None) or (
            getattr(contact.web_profile, "website_url", None) if getattr(contact, "web_profile", None) else None
        )
        existing_row = self._get(f"CONTACT#{rec_id}") or (
            self._contact_by_name(contact.person_name) if contact.person_name else None
        )
        if existing_row:
            if not getattr(contact, "web_profile", None) and existing_row.get("web_profile_json"):
                web_profile_str = existing_row["web_profile_json"]
            elif getattr(contact, "web_profile", None):
                web_profile_str = contact.web_profile.model_dump_json()
            if not website_url_val and existing_row.get("website_url"):
                website_url_val = existing_row["website_url"]
        elif getattr(contact, "web_profile", None):
            web_profile_str = contact.web_profile.model_dump_json()
        if website_url_val and hasattr(contact, "website_url"):
            contact.website_url = website_url_val

        row = {
            "id": rec_id, "person_name": contact.person_name, "company_or_role": contact.company_or_role,
            "contact_info": contact.contact_info,
            "commitments_json": json.dumps(commitments_payload, ensure_ascii=False),
            "key_topics_json": json.dumps(contact.key_topics, ensure_ascii=False), "timestamp": contact.timestamp,
            "web_profile_json": web_profile_str, "location_encountered": contact.location_encountered,
            "session_id": contact.session_id, "website_url": website_url_val,
        }
        ops = [self.table.tx_put(self._item(f"CONTACT#{rec_id}", row))]
        name_key = rules.contact_name_key(contact.person_name)
        if name_key:
            # The guard points to the latest contact saved with this name (SQLite keeps the newest row)
            ops.append(self.table.tx_put(self._item(f"CONTACTNAME#{name_key}", {"contact_id": rec_id})))
        stored = existing_row if existing_row and existing_row.get("id") == rec_id else None
        old_key = rules.contact_name_key(stored.get("person_name")) if stored else ""
        if old_key and old_key != name_key:
            e = Expr()
            release = self.table.tx_delete(self._key(f"CONTACTNAME#{old_key}"),
                                           condition=f"{e.name('contact_id')} = {e.value(rec_id)}", expr=e)
            try:
                self.table.transact(ops + [release])
                return rec_id
            except Exception as err:
                if not is_conditional_failure(err):
                    raise
                # the old name already points to another contact: leave that guard alone
        self.table.transact(ops)
        return rec_id

    def _contact_model(self, row: Dict[str, Any]) -> SocialEntity:
        return rules.row_to_contact(row, self.list_social_commitments(contact_name=row["person_name"]))

    def get_social_contact(self, contact_id_or_name: str) -> Optional[SocialEntity]:
        target = contact_id_or_name.strip()
        candidates = [r for r in (self._get(f"CONTACT#{target}"), self._contact_by_name(target)) if r]
        if not candidates:
            return None
        return self._contact_model(max(candidates, key=lambda r: r.get("timestamp") or ""))

    def update_contact_web_profile(
        self, contact_id_or_name: str, profile: SocialWebProfile
    ) -> bool:
        target = contact_id_or_name.strip()
        if _UUID.match(target):
            contact_id = target
        else:
            guard = self._get(f"CONTACTNAME#{rules.contact_name_key(target)}")
            if not guard:
                return False
            contact_id = guard["contact_id"]
        try:
            self.table.update(
                self._key(f"CONTACT#{contact_id}"), set_={"web_profile_json": profile.model_dump_json()},
                set_if_absent={"website_url": profile.website_url} if profile.website_url else None,
                condition="attribute_exists(sk)",
            )
            return True
        except Exception as e:
            if is_conditional_failure(e):
                return False
            raise

    def search_social_contact(self, query: str) -> List[SocialEntity]:
        pattern = f"%{query.strip().lower()}%"
        rows = [
            r for r in self._prefix("CONTACT#")
            if rules.sql_like(_ascii_lower(r.get("person_name")), pattern)
            or rules.sql_like(_ascii_lower(r.get("company_or_role")) if r.get("company_or_role") is not None else None, pattern)
            or rules.sql_like(_ascii_lower(r.get("key_topics_json")) if r.get("key_topics_json") is not None else None, pattern)
        ]
        rows.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
        return [self._contact_model(r) for r in rows]

    def save_social_commitment(self, commitment: SocialCommitment) -> str:
        key = rules.commitment_key(commitment.contact_name, commitment.description, commitment.debtor)
        rec_id = commitment.id
        for _ in range(_MAX_RETRIES):
            guard = self._get(f"COMMITKEY#{key}")
            existing = self._get(f"COMMIT#{guard['commitment_id']}") if guard else None
            if existing:
                rec_id = existing["id"]
                if not commitment.auto_scheduled_task_id and existing.get("auto_scheduled_task_id"):
                    commitment.auto_scheduled_task_id = existing["auto_scheduled_task_id"]
                if not commitment.created_at and existing.get("created_at"):
                    commitment.created_at = existing["created_at"]
            if not rec_id:
                rec_id = str(uuid.uuid4())
            commitment.id = rec_id
            if not commitment.created_at:
                commitment.created_at = _now_iso()
            row = {
                "id": rec_id, "contact_name": commitment.contact_name, "debtor": commitment.debtor,
                "description": commitment.description, "due_date_raw": commitment.due_date_raw,
                "normalized_deadline": commitment.normalized_deadline, "status": commitment.status,
                "auto_scheduled_task_id": commitment.auto_scheduled_task_id, "created_at": commitment.created_at,
            }
            e = Expr()
            guard_cond = f"attribute_not_exists(sk) OR {e.name('commitment_id')} = {e.value(rec_id)}"
            try:
                self.table.transact([
                    self.table.tx_put(self._item(f"COMMIT#{rec_id}", row)),
                    self.table.tx_put(self._item(f"COMMITKEY#{key}", {"commitment_id": rec_id}),
                                      condition=guard_cond, expr=e),
                ])
                break
            except Exception as err:
                if not is_conditional_failure(err):
                    raise
                rec_id = None  # another writer created it first: adopt its id
        else:
            raise RuntimeError("commitment could not be saved after concurrent updates")

        # Milestone 1.3: automatic agenda provisioning for the user's own promises
        if commitment.debtor == "user" and not commitment.auto_scheduled_task_id and commitment.status == "open":
            planned_task = PlannedTask(
                title=f"{commitment.description} (Promise to {commitment.contact_name})",
                domain="personal", scheduled_time=commitment.normalized_deadline or None, recurrence="none",
                status="pending", origin="social_commitment", raw_statement=commitment.description, confidence=1.0,
            )
            task_id = self.save_planned_task(planned_task)
            try:
                self.table.update(self._key(f"COMMIT#{rec_id}"), set_={"auto_scheduled_task_id": task_id},
                                  condition="attribute_exists(sk) AND attribute_not_exists(auto_scheduled_task_id)")
                commitment.auto_scheduled_task_id = task_id
            except Exception as err:
                if not is_conditional_failure(err):
                    raise
                self.delete_planned_task(task_id)  # a concurrent writer already scheduled it
                stored = self._get(f"COMMIT#{rec_id}")
                commitment.auto_scheduled_task_id = stored.get("auto_scheduled_task_id") if stored else None
        return rec_id

    def get_social_commitment(self, commitment_id: str) -> Optional[SocialCommitment]:
        item = self._get(f"COMMIT#{commitment_id}")
        return rules.row_to_commitment(item) if item else None

    def list_social_commitments(
        self,
        contact_name: Optional[str] = None,
        debtor: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SocialCommitment]:
        wanted = _ascii_lower(contact_name.strip()) if contact_name else None
        rows = [
            r for r in self._prefix("COMMIT#")
            if (wanted is None or _ascii_lower(r.get("contact_name")) == wanted)
            and (not debtor or r.get("debtor") == debtor)
            and (not status or r.get("status") == status)
        ]
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return [rules.row_to_commitment(r) for r in rows[:max(0, limit)]]

    def update_social_commitment_status(self, commitment_id: str, status: str) -> bool:
        commitment = self.get_social_commitment(commitment_id)
        if not commitment:
            return False
        self._update_existing(f"COMMIT#{commitment_id}", {"status": status})
        if status == "fulfilled" and commitment.auto_scheduled_task_id:
            self.complete_planned_task(task_id=commitment.auto_scheduled_task_id,
                                       verified_action_id="commitment_fulfilled", completed_at=_now_iso())
        elif status == "cancelled" and commitment.auto_scheduled_task_id:
            task = self.get_planned_task(commitment.auto_scheduled_task_id)
            if task:
                task.status = "cancelled"
                self.update_planned_task(task)
        return True

    def delete_social_commitment(self, commitment_id: str) -> bool:
        commitment = self.get_social_commitment(commitment_id)
        if not commitment:
            return False
        key = rules.commitment_key(commitment.contact_name, commitment.description, commitment.debtor)
        e = Expr()
        try:
            self.table.transact([
                self.table.tx_delete(self._key(f"COMMIT#{commitment_id}")),
                self.table.tx_delete(self._key(f"COMMITKEY#{key}"),
                                     condition=f"attribute_not_exists(sk) OR {e.name('commitment_id')} = {e.value(commitment_id)}",
                                     expr=e),
            ])
        except Exception as err:
            if not is_conditional_failure(err):
                raise
            self.table.delete(self._key(f"COMMIT#{commitment_id}"))
        if commitment.auto_scheduled_task_id:
            try:
                self.delete_planned_task(commitment.auto_scheduled_task_id)
            except Exception:
                pass
        return True

    # ------------------------------------------------------------------
    # Topic intelligence
    # ------------------------------------------------------------------
    def save_topic_briefing(self, briefing: BriefingReport) -> str:
        rec_id = briefing.id or str(uuid.uuid4())
        briefing.id = rec_id
        row = {
            "id": rec_id, "topic_title": briefing.topic_title, "context_type": briefing.context_type,
            "executive_summary_json": json.dumps(briefing.executive_summary, ensure_ascii=False),
            "explanatory_synthesis": briefing.explanatory_synthesis or "",
            "deep_dive_markdown": briefing.deep_dive_markdown,
            "web_sources_json": json.dumps(briefing.web_sources, ensure_ascii=False),
            "action_items_json": json.dumps(briefing.action_items, ensure_ascii=False),
            "created_at": briefing.created_at, "session_id": briefing.session_id, "segment_id": briefing.segment_id,
            "kind": briefing.kind,
        }
        self.table.put(self._item(f"BRIEF#{rec_id}", row, **self._briefing_index(rec_id, briefing.created_at,
                                                                                  briefing.session_id)),
                       what="briefing")
        return rec_id

    def _briefing_index(self, rec_id: str, created_at: str, session_id: Optional[str]) -> Dict[str, Any]:
        index = {"g2pk": self._gpk("BRIEF"), "g2sk": f"{created_at}#{rec_id}"}
        if session_id:
            index.update(g3pk=self._gpk(f"SESSION#{key_part(session_id)}"), g3sk=f"{created_at}#{rec_id}")
        return index

    def get_topic_briefing(self, query: Optional[str] = None) -> Optional[BriefingReport]:
        if not (query and query.strip()):
            for key in self._index(self._g2, self._gpk("BRIEF"), forward=False, page_size=1):
                item = self._get(key["sk"])
                if item:
                    return rules.row_to_briefing(item)
            return None
        target = query.strip()
        by_id = self._get(f"BRIEF#{target}")
        if by_id:
            return rules.row_to_briefing(by_id)
        pattern = f"%{target.lower()}%"
        page: List[Dict[str, Any]] = []

        def first_match(keys: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            for item in self._full(keys):
                if (rules.sql_like(_ascii_lower(item.get("topic_title")), pattern)
                        or rules.sql_like(_ascii_lower(item.get("deep_dive_markdown"))
                                          if item.get("deep_dive_markdown") is not None else None, pattern)
                        or rules.sql_like(_ascii_lower(item.get("explanatory_synthesis") or ""), pattern)):
                    return item
            return None

        for key in self._index(self._g2, self._gpk("BRIEF"), forward=False, page_size=100):
            page.append(key)
            if len(page) == 100:
                found = first_match(page)
                if found:
                    return rules.row_to_briefing(found)
                page = []
        found = first_match(page) if page else None
        return rules.row_to_briefing(found) if found else None

    def list_topic_briefings(
        self, limit: int = 10, kind: Optional[str] = None, session_id: Optional[str] = None
    ) -> List[BriefingReport]:
        if session_id:
            keys = self._index(self._g3, self._gpk(f"SESSION#{key_part(session_id)}"), forward=False)
        else:
            keys = self._index(self._g2, self._gpk("BRIEF"), forward=False)
        selected = []
        for key in keys:
            if kind and key.get("kind") != kind:
                continue
            if session_id and key.get("session_id") != session_id:
                continue
            selected.append(key)
            if len(selected) >= limit:
                break
        return [rules.row_to_briefing(item) for item in self._full(selected)]

    def list_briefings_for_session(self, session_id: str) -> List[BriefingReport]:
        keys = [k for k in self._index(self._g3, self._gpk(f"SESSION#{key_part(session_id)}"))
                if k.get("session_id") == session_id]
        return [rules.row_to_briefing(item) for item in self._full(keys)]

    def delete_topic_briefing(self, briefing_id: str) -> bool:
        return self.table.delete(self._key(f"BRIEF#{briefing_id}"), return_old=True) is not None

    def reassign_briefings(self, briefing_ids: List[str], session_id: str) -> None:
        for briefing_id in briefing_ids or []:
            item = self._get(f"BRIEF#{briefing_id}")
            if not item:
                continue
            index = self._briefing_index(briefing_id, item["created_at"], session_id)
            self.table.update(self._key(f"BRIEF#{briefing_id}"),
                              set_={"session_id": session_id, "g3pk": index["g3pk"], "g3sk": index["g3sk"]})

    def patch_utterance_speaker(
        self, chunk_id: str, speaker_id: str, speaker_role: Optional[str] = None
    ) -> bool:
        """Records a late speaker identity (Bee `tagged-utterance`); only the diarization item is written."""
        self.table.put(self._item(f"DIAR#{chunk_id}", {
            "chunk_id": chunk_id, "speaker_id": speaker_id, "speaker_role": speaker_role or "unknown",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }))
        return True

    # ------------------------------------------------------------------
    # Session dossiers / events
    # ------------------------------------------------------------------
    def _chunk_prefix(self, session_id: str) -> str:
        return f"CHUNK#{key_part(session_id)}#"

    def _has_chunks(self, session_id: str) -> bool:
        for _ in self._prefix(self._chunk_prefix(session_id), attributes=["sk"], limit=1):
            return True
        return False

    def _dossier_item(self, dossier: SessionDossier, version: int) -> Dict[str, Any]:
        chunks_str = None if self._has_chunks(dossier.session_id) else json.dumps(dossier.transcript_chunks,
                                                                                  ensure_ascii=False)
        cols = rules.dossier_columns(dossier, chunks_str)
        sid = key_part(dossier.session_id)
        return self._item(
            f"DOSSIER#{dossier.session_id}", cols, version=version,
            g2pk=self._gpk("DOSSIER"), g2sk=f"{cols['start_time']}#{sid}",
            g3pk=self._gpk(f"DSTATE#{dossier_state(cols)}"), g3sk=f"{cols['last_updated_at']}#{sid}",
        )

    def _write_dossier(self, item: Dict[str, Any], condition: str, expr: Expr) -> None:
        """UpdateItem of every dossier attribute: ``link_versions_json`` (owned by
        ``link_micro_event_to_session``) survives the engine's saves."""
        packed = pack(item, "dossier")
        columns = COLUMNS["session_dossiers"]
        remove = [c for c in columns if c not in packed]
        remove += [f"{c}__z" for c in columns if f"{c}__z" not in packed]
        if "compressed" not in packed:
            remove.append("compressed")
        self.table.update({"pk": packed["pk"], "sk": packed["sk"]},
                          set_={k: v for k, v in packed.items() if k not in ("pk", "sk")},
                          remove=remove, condition=condition, expr=expr)

    def save_session_dossier(self, dossier: SessionDossier) -> str:
        for _ in range(_MAX_RETRIES):
            expected = dossier._store_version
            e = Expr()
            condition = (f"{e.name('version')} = {e.value(expected)}" if expected
                         else "attribute_not_exists(sk)")
            try:
                self._write_dossier(self._dossier_item(dossier, expected + 1), condition, e)
                dossier._store_version = expected + 1
                return dossier.session_id
            except Exception as err:
                if not is_conditional_failure(err):
                    raise
            # Someone else wrote the dossier after our read: keep the micro-event links they added.
            # Links the caller had already seen (added at or before its version) and dropped stay dropped.
            persisted = self._get(f"DOSSIER#{dossier.session_id}")
            if persisted is None:
                dossier._store_version = 0
                continue
            added_at = json.loads(persisted.get("link_versions_json") or "{}")
            known = {(ref.event_type, ref.record_id) for ref in dossier.linked_micro_events}
            for ref in rules.row_to_dossier(persisted, None, None).linked_micro_events:
                if (ref.event_type, ref.record_id) not in known and \
                        int(added_at.get(f"{ref.event_type}#{ref.record_id}", 0)) > expected:
                    dossier.linked_micro_events.append(ref)
            dossier._store_version = int(persisted.get("version") or 0)
            try:
                from src.core.metrics import metrics

                metrics.incr("storage.conditional_conflicts")
            except Exception:
                pass
        raise RuntimeError("dossier could not be saved after concurrent updates")

    def _to_dossier(self, item: Dict[str, Any], include_chunks: bool = True) -> SessionDossier:
        chunks: List[str] = []
        if include_chunks:
            rows = list(itertools.islice(self._prefix(self._chunk_prefix(item["session_id"]), forward=False,
                                                      attributes=["text"], limit=200), 200))
            chunks = [r["text"] for r in reversed(rows)]
        briefing = self.get_topic_briefing(item["final_briefing_id"]) if item.get("final_briefing_id") else None
        dossier = rules.row_to_dossier(item, chunks, briefing)
        dossier._store_version = int(item.get("version") or 0)
        return dossier

    def _latest_dossier_key(self) -> Optional[Dict[str, Any]]:
        best = None
        for state in ("open", "pending_final", "closed"):
            for key in self._index(self._g3, self._gpk(f"DSTATE#{state}"), forward=False, page_size=1):
                if best is None or key["g3sk"] > best["g3sk"]:
                    best = key
                break
        return best

    def get_session_dossier(
        self, session_id: Optional[str] = None, include_chunks: bool = True
    ) -> Optional[SessionDossier]:
        if session_id:
            item = self._get(f"DOSSIER#{session_id}")
        else:
            key = self._latest_dossier_key()
            item = self._get(key["sk"]) if key else None
        return self._to_dossier(item, include_chunks) if item else None

    def list_session_dossiers(
        self,
        status: Optional[str] = None,
        limit: int = 10,
        ingest_source: Optional[str] = None,
        ingest_run_id: Optional[str] = None,
    ) -> List[SessionDossier]:
        selected = []
        for key in self._index(self._g2, self._gpk("DOSSIER"), forward=False):
            if status and key.get("status") != status:
                continue
            if ingest_source and key.get("ingest_source") != ingest_source:
                continue
            if ingest_run_id and key.get("ingest_run_id") != ingest_run_id:
                continue
            selected.append(key)
            if len(selected) >= limit:
                break
        return [self._to_dossier(item) for item in self._full(selected)]

    def _confirmed(self, state: str, forward: bool, ingest_source: Optional[str], run_id: Optional[str],
                   accept: Callable[[Dict[str, Any]], bool], limit: int) -> List[SessionDossier]:
        out = []
        for key in self._index(self._g3, self._gpk(f"DSTATE#{state}"), forward=forward):
            if ingest_source and (key.get("ingest_source") or "live") != ingest_source:
                continue
            if run_id and key.get("ingest_run_id") != run_id:
                continue
            item = self._get(key["sk"])  # confirm-on-read: the index may lag behind the item
            if not item or not accept(item):
                continue
            if ingest_source and (item.get("ingest_source") or "live") != ingest_source:
                continue
            out.append(self._to_dossier(item))
            if len(out) >= limit:
                break
        return out

    def get_open_event(
        self, ingest_source: str = "live", run_id: Optional[str] = None
    ) -> Optional[SessionDossier]:
        found = self._confirmed("open", False, ingest_source, run_id,
                                lambda i: dossier_state(i) == "open", 1)
        return found[0] if found else None

    def list_events_pending_final(
        self, limit: int = 20, ingest_source: Optional[str] = None, run_id: Optional[str] = None
    ) -> List[SessionDossier]:
        return self._confirmed("pending_final", True, ingest_source, run_id,
                               lambda i: dossier_state(i) == "pending_final", limit)

    def delete_session_dossier(self, session_id: str) -> bool:
        return self.table.delete(self._key(f"DOSSIER#{session_id}"), return_old=True) is not None

    def append_chunk_to_session(
        self, session_id: str, chunk_text: str, location: Optional[dict] = None
    ) -> SessionDossier:
        dossier = self.get_session_dossier(session_id)
        now_iso = _now_iso()
        if not dossier:
            dossier = SessionDossier(
                session_id=session_id, title=f"Session {session_id[:8]}", domain="meeting", start_time=now_iso,
                last_updated_at=now_iso, status="active", location=location,
                transcript_chunks=[chunk_text] if chunk_text and chunk_text.strip() else [],
            )
        elif dossier.status == "concluded":
            logger.warning(f"Refusing to append chunk to concluded session '{session_id}'.")
            return dossier
        else:
            if chunk_text and chunk_text.strip():
                dossier.transcript_chunks.append(chunk_text.strip())
            dossier.last_updated_at = now_iso
            if location:
                dossier.location = location
        self.save_session_dossier(dossier)
        return dossier

    def link_micro_event_to_session(self, session_id: str, event_ref: Any) -> bool:
        if isinstance(event_ref, dict):
            event_ref = MicroEventRef(**event_ref)
        elif not isinstance(event_ref, MicroEventRef):
            return False
        for _ in range(_MAX_RETRIES):
            item = self._get(f"DOSSIER#{session_id}")
            now_iso = _now_iso()
            if item is None:
                dossier = SessionDossier(
                    session_id=session_id, title=f"Session {session_id[:8]}", domain="meeting",
                    start_time=now_iso, last_updated_at=now_iso, status="active", linked_micro_events=[event_ref],
                )
                try:
                    self.save_session_dossier(dossier)
                    return True
                except RuntimeError:
                    continue
            dossier = rules.row_to_dossier(item, None, None)
            version = int(item.get("version") or 0)
            added_at = json.loads(item.get("link_versions_json") or "{}")
            if not any(e.record_id == event_ref.record_id and e.event_type == event_ref.event_type
                       for e in dossier.linked_micro_events):
                dossier.linked_micro_events.append(event_ref)
                added_at[f"{event_ref.event_type}#{event_ref.record_id}"] = version + 1
            # Only the micro-event attributes change. The lifecycle fields (owned by the event engine) are
            # written back as read: the version condition guarantees nobody changed them meanwhile. The whole
            # item goes through pack(), so a compressed dossier stays consistent and size-checked.
            payload = json.dumps([e.model_dump() for e in dossier.linked_micro_events], ensure_ascii=False)
            e = Expr()
            condition = f"{e.name('version')} = {e.value(version)}" if version else "attribute_not_exists(version)"
            sid = key_part(session_id)
            updated = {**item, "linked_micro_events_json": payload, "link_versions_json": json.dumps(added_at),
                       "last_updated_at": now_iso, "version": version + 1, "g3sk": f"{now_iso}#{sid}"}
            try:
                self._write_dossier(updated, condition, e)
                return True
            except Exception as err:
                if not is_conditional_failure(err):
                    raise
        raise RuntimeError("micro-event link could not be saved after concurrent updates")

    def conclude_session_dossier(
        self, session_id: str, briefing_report_id: Optional[str] = None
    ) -> Optional[SessionDossier]:
        dossier = self.get_session_dossier(session_id)
        if not dossier:
            return None
        now_iso = _now_iso()
        dossier.status = "concluded"
        dossier.concluded_at = now_iso
        dossier.last_updated_at = now_iso
        if briefing_report_id:
            dossier.final_briefing_id = briefing_report_id
            dossier.briefing_report = self.get_topic_briefing(briefing_report_id)
        self.save_session_dossier(dossier)
        return dossier

    # ------------------------------------------------------------------
    # Per-chunk event log
    # ------------------------------------------------------------------
    def _chunk_sk(self, session_id: str, ts: str, seq: int) -> str:
        return f"{self._chunk_prefix(session_id)}{ts}#{seq:020d}"

    def append_session_chunk(
        self, chunk: UtteranceChunk, session_id: str, segment_id: Optional[str] = None, on_topic: bool = False
    ) -> None:
        """Appends one utterance to the per-chunk event log (idempotent on chunk_id)."""
        ref = self._get(f"CHUNKREF#{chunk.chunk_id}")
        seq = int(ref["seq"]) if ref else time.time_ns()
        new_sk = self._chunk_sk(session_id, chunk.timestamp, seq)
        row = {
            "chunk_id": chunk.chunk_id, "session_id": session_id, "segment_id": segment_id,
            "conversation_uuid": chunk.conversation_uuid, "ts": chunk.timestamp, "text": chunk.text,
            "word_count": len(chunk.text.split()), "speaker_id": chunk.speaker_id, "speaker_role": chunk.speaker_role,
            "categories_json": json.dumps(chunk.categories, ensure_ascii=False), "on_topic": 1 if on_topic else 0,
            "location_json": json.dumps(chunk.location, ensure_ascii=False) if chunk.location else None,
        }
        item = self._item(new_sk, row, seq=seq)
        if ref and ref.get("chunk_sk") == new_sk:
            self.table.put(item, what="chunk")
            return
        ops = [self.table.tx_put(item),
               self.table.tx_put(self._item(f"CHUNKREF#{chunk.chunk_id}", {"chunk_sk": new_sk, "seq": seq,
                                                                         "session_id": session_id}))]
        if ref and ref.get("chunk_sk"):
            ops.append(self.table.tx_delete(self._key(ref["chunk_sk"])))
        self.table.transact(ops)

    @staticmethod
    def _to_chunk(row: Dict[str, Any]) -> UtteranceChunk:
        return UtteranceChunk(
            chunk_id=row["chunk_id"],
            conversation_uuid=row.get("conversation_uuid") or "default_session",
            text=row["text"],
            speaker_id=row.get("speaker_id"),
            speaker_role=row.get("speaker_role") or "unknown",
            timestamp=row["ts"],
            categories=json.loads(row["categories_json"]) if row.get("categories_json") else [],
            location=json.loads(row["location_json"]) if row.get("location_json") else None,
        )

    def list_session_chunks(
        self,
        session_id: str,
        segment_id: Optional[str] = None,
        in_segments_only: bool = False,
        limit: Optional[int] = None,
    ) -> List[UtteranceChunk]:
        out = []
        for row in self._prefix(self._chunk_prefix(session_id)):
            if row.get("session_id") != session_id:
                continue
            if segment_id and row.get("segment_id") != segment_id:
                continue
            if not segment_id and in_segments_only and row.get("segment_id") is None:
                continue
            out.append(self._to_chunk(row))
            if limit and len(out) >= limit:
                break
        return out

    def get_chunk_segments(self, session_id: str) -> Dict[str, Optional[str]]:
        return {
            row["chunk_id"]: row.get("segment_id")
            for row in self._prefix(self._chunk_prefix(session_id), attributes=["chunk_id", "segment_id", "session_id"])
            if row.get("session_id") == session_id
        }

    def assign_chunks(
        self,
        chunk_ids: List[str],
        session_id: str,
        segment_id: Optional[str],
        on_topic: Optional[bool] = None,
    ) -> None:
        """Moves logged chunks to an event/segment. At most 33 chunks move per transaction; every step is
        idempotent, so a retry after a partial failure completes the move."""
        if not chunk_ids:
            return
        refs = self.table.batch_get([self._key(f"CHUNKREF#{cid}") for cid in dict.fromkeys(chunk_ids)])
        chunks = {c["sk"]: c for c in self.table.batch_get([self._key(r["chunk_sk"]) for r in refs if r.get("chunk_sk")])}
        ops: List[Dict[str, Any]] = []
        for ref in refs:
            row = chunks.get(ref.get("chunk_sk"))
            if row is None:
                continue
            changes: Dict[str, Any] = {"session_id": session_id, "segment_id": segment_id}
            if on_topic is not None:
                changes["on_topic"] = 1 if on_topic else 0
            if row.get("session_id") == session_id:
                self.table.update(self._key(row["sk"]), set_=changes)
                continue
            moved = {k: v for k, v in row.items() if k not in ("pk", "sk", "segment_id")}
            moved.update({k: v for k, v in changes.items() if v is not None})
            new_sk = self._chunk_sk(session_id, row["ts"], int(row["seq"]))
            ops += [
                self.table.tx_put(self._item(new_sk, moved)),
                self.table.tx_put(self._item(ref["sk"], {"chunk_sk": new_sk, "seq": int(row["seq"]),
                                                         "session_id": session_id})),
                self.table.tx_delete(self._key(row["sk"])),
            ]
            if len(ops) >= 99:
                self.table.transact(ops)
                ops = []
        self.table.transact(ops)

    # ------------------------------------------------------------------
    # Web search cache
    # ------------------------------------------------------------------
    @staticmethod
    def _cache_sk(query_norm: str) -> str:
        return "CACHE#" + hashlib.sha256(query_norm.encode("utf-8")).hexdigest()

    def get_cached_search(self, query_norm: str, max_age_seconds: int) -> Optional[dict]:
        item = self._get(self._cache_sk(query_norm))
        if not item or item.get("query_norm") != query_norm:
            return None
        try:
            age = (datetime.now() - datetime.fromisoformat(item["fetched_at"])).total_seconds()
        except (KeyError, ValueError):
            return None
        if age > max_age_seconds:
            return None
        return {"provider": item.get("provider"), "results": json.loads(item["results_json"])}

    def put_cached_search(self, query_norm: str, provider: str, results: List[dict]) -> None:
        from src.core.config import settings

        self.table.put(self._item(self._cache_sk(query_norm), {
            "query_norm": query_norm, "provider": provider,
            "results_json": json.dumps(results, ensure_ascii=False), "fetched_at": _now_iso(),
        }, ttl=_epoch_after(max(1, settings.web_search_cache_ttl_seconds) / 86400)), what="search cache")

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------
    def record_latency(
        self,
        event_type: str,
        latency_ms: float,
        model_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        from src.core.config import settings

        ts = _now_iso()
        rec_id = uuid.uuid4().hex
        try:
            self.table.put(self._item(f"TEL#{ts}#{rec_id[:8]}", {
                "id": rec_id, "timestamp": ts, "event_type": event_type, "latency_ms": float(latency_ms),
                "model_id": model_id, "details_json": json.dumps(details or {}, ensure_ascii=False),
            }, ttl=_epoch_after(settings.dynamo_telemetry_ttl_days)))
        except Exception as e:
            logger.warning(f"Failed to record system telemetry: {type(e).__name__}")

    def get_latency_metrics(self, event_type: Optional[str] = None, limit: int = 50) -> dict:
        values: List[float] = []
        try:
            for row in self._prefix("TEL#", forward=False):
                kind = row.get("event_type") or ""
                if event_type and kind != event_type:
                    continue
                if not event_type and rules.sql_like(kind, "backfill%"):
                    continue
                values.append(float(row["latency_ms"]))
                if len(values) >= limit:
                    break
        except Exception as e:
            logger.warning(f"Failed to query latency metrics: {type(e).__name__}")
            return rules.latency_summary([])
        return rules.latency_summary(values)

    # ------------------------------------------------------------------
    # Historical transcript backfill
    # ------------------------------------------------------------------
    def save_coverage_interval(self, interval: CoverageInterval) -> str:
        self.table.put(self._item(f"COV#{interval.id}", {
            "id": interval.id, "source": interval.source, "start_ts": interval.start, "end_ts": interval.end,
            "is_open": 1 if interval.is_open else 0, "degraded": 1 if interval.degraded else 0,
            "run_id": interval.run_id, "utterances": interval.utterances, "errors": interval.errors,
        }))
        return interval.id

    def list_coverage(
        self, start: Optional[str] = None, end: Optional[str] = None, source: Optional[str] = None
    ) -> List[CoverageInterval]:
        rows = [
            r for r in self._prefix("COV#")
            if (not start or (r.get("end_ts") or "") >= start)
            and (not end or (r.get("start_ts") or "") <= end)
            and (not source or r.get("source") == source)
        ]
        rows.sort(key=lambda r: r.get("start_ts") or "")
        return [rules.row_to_coverage(r) for r in rows]

    def close_open_coverage_intervals(self, source: str = "live") -> int:
        closed = 0
        for row in self._prefix("COV#"):
            if row.get("is_open") == 1 and row.get("source") == source:
                self.table.update(self._key(row["sk"]), set_={"is_open": 0})
                closed += 1
        return closed

    def last_coverage_end(self, source: Optional[str] = None) -> Optional[str]:
        ends = [r["end_ts"] for r in self._prefix("COV#", attributes=["end_ts", "source"])
                if r.get("end_ts") is not None and (not source or r.get("source") == source)]
        return max(ends) if ends else None

    def record_ingested_utterance(self, entry: Dict[str, Any]) -> None:
        received_at = entry.get("received_at")
        ledger_time = received_at if received_at is not None else entry["ts"]
        self.table.put(self._item(f"LEDGER#{entry['source_key']}", {
            "source_key": entry["source_key"], "source": entry.get("source", "live"),
            "bee_conversation_uuid": entry.get("bee_conversation_uuid"),
            "bee_conversation_id": entry.get("bee_conversation_id"), "ts": entry["ts"], "received_at": received_at,
            "text_norm": entry.get("text_norm"), "text_hash": entry["text_hash"],
            "status": entry.get("status", "screened_noop"),
            "categories_json": json.dumps(entry.get("categories") or [], ensure_ascii=False),
            "run_id": entry.get("run_id"), "duration_ms": entry.get("duration_ms"),
        }, ledger_time=ledger_time, g1pk=self._gpk("LEDGER"), g1sk=f"{ledger_time}#{entry['source_key']}"))

    def get_ledger_entry(self, source_key: str) -> Optional[Dict[str, Any]]:
        item = self._get(f"LEDGER#{source_key}")
        return rules.row_to_ledger(item) if item else None

    def list_ledger_entries(
        self,
        t_from: str,
        t_to: str,
        source: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Ledger rows whose receive time (live) or spoken time falls within [t_from, t_to]."""
        out = []
        for row in self._index(self._g1, self._gpk("LEDGER"), between=(t_from, f"{t_to}#{_HIGH}")):
            lt = row.get("ledger_time") or ""
            if not (t_from <= lt <= t_to):
                continue
            if source and row.get("source") != source:
                continue
            if status and row.get("status") != status:
                continue
            out.append(rules.row_to_ledger(row))
        return out

    def purge_ingest_ledger(self, before: str) -> int:
        doomed = [row["sk"] for row in self._index(self._g1, self._gpk("LEDGER"), lt=before)
                  if (row.get("ledger_time") or "") < before]
        self._delete_keys(doomed)
        return len(doomed)

    def map_bee_conversation(self, conv_uuid: str, conv_id: Optional[int]) -> None:
        if not conv_uuid:
            return
        previous = self.table.update(
            self._key(f"BEECONV#{conv_uuid}"),
            set_={"uuid": conv_uuid, **({"id": int(conv_id)} if conv_id is not None else {})},
            set_if_absent={"first_seen_at": _now_iso()}, return_values="ALL_OLD",
        )
        if conv_id is None:
            return
        old_id = (previous or {}).get("id")
        if old_id is not None and int(old_id) != int(conv_id):
            e = Expr()
            try:
                self.table.delete(self._key(f"BEECONVID#{old_id}"),
                                  condition=f"{e.name('uuid')} = {e.value(conv_uuid)}", expr=e)
            except Exception as err:
                if not is_conditional_failure(err):
                    raise
        self.table.put(self._item(f"BEECONVID#{int(conv_id)}", {"uuid": conv_uuid}))

    def get_bee_conversation_uuid(self, conv_id: int) -> Optional[str]:
        item = self._get(f"BEECONVID#{int(conv_id)}")
        return item.get("uuid") if item else None

    def save_backfill_run(self, run: BackfillRun) -> str:
        self.table.put(self._item(f"RUN#{run.id}", {
            "id": run.id, "trigger": run.trigger, "window_from": run.window_from, "window_to": run.window_to,
            "status": run.status, "payload_json": run.model_dump_json(), "created_at": run.created_at,
        }), what="backfill run")
        return run.id

    def get_backfill_run(self, run_id: str) -> Optional[BackfillRun]:
        item = self._get(f"RUN#{run_id}")
        return BackfillRun.model_validate_json(item["payload_json"]) if item else None

    def list_backfill_runs(self, statuses: Optional[List[str]] = None, limit: int = 20) -> List[BackfillRun]:
        rows = [r for r in self._prefix("RUN#") if not statuses or r.get("status") in statuses]
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return [BackfillRun.model_validate_json(r["payload_json"]) for r in rows[:max(0, limit)]]

    def purge_ingestion_history(self) -> None:
        """GDPR erasure of the backfill bookkeeping (coverage, ledger text, conversation map, runs)."""
        for prefix in HISTORY_PREFIXES:
            self._delete_keys([row["sk"] for row in self._prefix(prefix, attributes=["sk"])])

    # ------------------------------------------------------------------
    # Whole partition
    # ------------------------------------------------------------------
    def export_all(self) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        for item in self.table.query("pk", self.user_id):
            prefix = item["sk"].split("#", 1)[0]
            table = PREFIX_TABLE.get(prefix)
            if table is None:
                continue
            out.setdefault(table, []).append({column: item.get(column) for column in COLUMNS[table]})
        return out

    def delete_all_data(self) -> None:
        self._delete_keys([item["sk"] for item in self.table.query("pk", self.user_id, attributes=["sk"])])

    def close(self) -> None:
        """The boto3 client is shared: nothing to close."""

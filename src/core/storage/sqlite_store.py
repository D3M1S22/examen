from datetime import datetime, timezone
import json
import logging
import os
import re
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Union

from src.core.schemas import (
    ActionChanges,
    BackfillPlan,
    BackfillRun,
    BriefingReport,
    ContactChanges,
    ContactDeletion,
    ContactUpdate,
    CoverageInterval,
    EventDeletion,
    MicroEventRef,
    PlannedTask,
    SessionDossier,
    SocialCommitment,
    SocialEntity,
    SocialWebProfile,
    RevokeResult,
    SpeakerAttribution,
    UtteranceChunk,
    VerifiedAction,
)
from src.core.storage import rules
from src.core.storage.base import AbstractContextStore
from src.core.storage.errors import UniqueConflict
from src.core.time_utils import historical_action_may_resolve

logger = logging.getLogger("examen.storage.sqlite")


class SQLiteContextStore(AbstractContextStore):
    """Local SQLite context database with FTS5 indexing."""

    def __init__(self, db_path: str = "examen.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        # Recreate the schema if the database file was deleted underneath a live
        # store instance (e.g. /reset-db while the server or tester is running).
        needs_schema = self.db_path != ":memory:" and not os.path.exists(self.db_path)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        if needs_schema:
            self._init_db()
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 0. Planned Tasks Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS planned_tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    scheduled_time TEXT,
                    recurrence TEXT NOT NULL DEFAULT 'none',
                    status TEXT NOT NULL DEFAULT 'pending',
                    completed_at TEXT,
                    verified_action_id TEXT,
                    created_at TEXT NOT NULL,
                    origin TEXT NOT NULL DEFAULT 'manual',
                    raw_statement TEXT,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    relative_time_anchor TEXT,
                    session_id TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_planned_status ON planned_tasks (status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_planned_time ON planned_tasks (scheduled_time);")
            for col_name, col_type in [
                ("origin", "TEXT NOT NULL DEFAULT 'manual'"),
                ("raw_statement", "TEXT"),
                ("confidence", "REAL NOT NULL DEFAULT 1.0"),
                ("relative_time_anchor", "TEXT"),
                ("session_id", "TEXT"),
                ("location_json", "TEXT"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE planned_tasks ADD COLUMN {col_name} {col_type};")
                except Exception:
                    pass
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_planned_origin ON planned_tasks (origin);")

            # 1. Verified Actions Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS verified_actions (
                    id TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    raw_statement TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    is_revoked INTEGER DEFAULT 0,
                    matched_task_id TEXT,
                    location_json TEXT,
                    session_id TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_type ON verified_actions (action_type);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_time ON verified_actions (timestamp DESC);")
            try:
                cursor.execute("ALTER TABLE verified_actions ADD COLUMN location_json TEXT;")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE verified_actions ADD COLUMN session_id TEXT;")
            except Exception:
                pass

            # 2. Social Contacts Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS social_contacts (
                    id TEXT PRIMARY KEY,
                    person_name TEXT NOT NULL,
                    company_or_role TEXT,
                    contact_info TEXT,
                    commitments_json TEXT,
                    key_topics_json TEXT,
                    timestamp TEXT NOT NULL,
                    web_profile_json TEXT,
                    location_encountered TEXT,
                    session_id TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_social_name ON social_contacts (person_name);")
            try:
                cursor.execute("ALTER TABLE social_contacts ADD COLUMN web_profile_json TEXT;")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE social_contacts ADD COLUMN location_encountered TEXT;")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE social_contacts ADD COLUMN session_id TEXT;")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE social_contacts ADD COLUMN website_url TEXT;")
            except Exception:
                pass

            # 2b. Social Commitments Table (Bilateral Promises - Milestone 1.3)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS social_commitments (
                    id TEXT PRIMARY KEY,
                    contact_name TEXT NOT NULL,
                    debtor TEXT NOT NULL CHECK(debtor IN ('user', 'contact')),
                    description TEXT NOT NULL,
                    due_date_raw TEXT,
                    normalized_deadline TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    auto_scheduled_task_id TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_commitments_contact ON social_commitments (contact_name);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_commitments_debtor ON social_commitments (debtor);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_commitments_status ON social_commitments (status);")

            # Purge duplicate commitments keeping earliest record to maintain clean relational state
            try:
                cursor.execute("""
                    DELETE FROM social_commitments
                    WHERE rowid NOT IN (
                        SELECT MIN(rowid)
                        FROM social_commitments
                        GROUP BY LOWER(contact_name), LOWER(description), debtor
                    );
                """)
            except Exception:
                pass

            # Purge duplicate contacts keeping most recent record
            try:
                cursor.execute("""
                    DELETE FROM social_contacts
                    WHERE rowid NOT IN (
                        SELECT MAX(rowid)
                        FROM social_contacts
                        GROUP BY LOWER(person_name)
                    );
                """)
            except Exception:
                pass

            # 3. Topic Briefings Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS topic_briefings (
                    id TEXT PRIMARY KEY,
                    topic_title TEXT NOT NULL,
                    context_type TEXT NOT NULL,
                    executive_summary_json TEXT,
                    explanatory_synthesis TEXT,
                    deep_dive_markdown TEXT,
                    web_sources_json TEXT,
                    action_items_json TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_briefings_time ON topic_briefings (created_at DESC);")
            try:
                cursor.execute("ALTER TABLE topic_briefings ADD COLUMN explanatory_synthesis TEXT;")
            except Exception:
                pass
            # Deep Topic Event Engine: briefing linkage to events/segments
            for ddl in (
                "ALTER TABLE topic_briefings ADD COLUMN session_id TEXT;",
                "ALTER TABLE topic_briefings ADD COLUMN segment_id TEXT;",
                "ALTER TABLE topic_briefings ADD COLUMN kind TEXT NOT NULL DEFAULT 'standalone';",
            ):
                try:
                    cursor.execute(ddl)
                except Exception:
                    pass
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_briefings_session ON topic_briefings (session_id, kind);")

            # 3b. Utterance Diarization Cache (Milestone 3.1)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS utterance_diarization (
                    chunk_id TEXT PRIMARY KEY,
                    speaker_id TEXT NOT NULL,
                    speaker_role TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_diarization_speaker ON utterance_diarization (speaker_id);")

            # 3c. Macro Session Dossiers Table (Milestone 3.2)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_dossiers (
                    session_id TEXT PRIMARY KEY,
                    title TEXT,
                    domain TEXT NOT NULL DEFAULT 'meeting',
                    start_time TEXT NOT NULL,
                    last_updated_at TEXT NOT NULL,
                    concluded_at TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    location_json TEXT,
                    transcript_chunks_json TEXT,
                    key_discussion_points_json TEXT,
                    linked_micro_events_json TEXT,
                    final_briefing_id TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON session_dossiers (status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_time ON session_dossiers (start_time DESC);")
            try:
                cursor.execute("ALTER TABLE verified_actions ADD COLUMN session_id TEXT;")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE social_contacts ADD COLUMN session_id TEXT;")
            except Exception:
                pass

            # 3d. Deep Topic Event Engine: event fields + per-chunk log
            for ddl in (
                "ALTER TABLE session_dossiers ADD COLUMN conversation_uuids_json TEXT;",
                "ALTER TABLE session_dossiers ADD COLUMN segments_json TEXT;",
                "ALTER TABLE session_dossiers ADD COLUMN anchor_location_json TEXT;",
                "ALTER TABLE session_dossiers ADD COLUMN last_on_topic_at TEXT;",
                "ALTER TABLE session_dossiers ADD COLUMN paused_at TEXT;",
                "ALTER TABLE session_dossiers ADD COLUMN hard_close_deadline TEXT;",
                "ALTER TABLE session_dossiers ADD COLUMN final_status TEXT NOT NULL DEFAULT 'none';",
                "ALTER TABLE session_dossiers ADD COLUMN final_revision INTEGER NOT NULL DEFAULT 0;",
                "ALTER TABLE session_dossiers ADD COLUMN transitions_json TEXT;",
                "ALTER TABLE session_dossiers ADD COLUMN research_ledger_json TEXT;",
                "ALTER TABLE session_dossiers ADD COLUMN topic_profile_json TEXT;",
                "ALTER TABLE session_dossiers ADD COLUMN pending_chunk_ids_json TEXT;",
            ):
                try:
                    cursor.execute(ddl)
                except Exception:
                    pass
            # Legacy 'finalizing' status maps to 'paused'
            cursor.execute(
                "UPDATE session_dossiers SET status = 'paused', paused_at = COALESCE(paused_at, last_updated_at) "
                "WHERE status = 'finalizing';"
            )
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    segment_id TEXT,
                    conversation_uuid TEXT,
                    ts TEXT NOT NULL,
                    text TEXT NOT NULL,
                    word_count INTEGER NOT NULL DEFAULT 0,
                    speaker_id TEXT,
                    speaker_role TEXT,
                    categories_json TEXT,
                    on_topic INTEGER NOT NULL DEFAULT 0,
                    location_json TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_chunks_session_ts ON session_chunks (session_id, ts);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_chunks_segment ON session_chunks (segment_id);")

            # 3e. Global web search cache (shared by event syntheses)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS web_search_cache (
                    query_norm TEXT PRIMARY KEY,
                    provider TEXT,
                    results_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                )
            """)

            # 3f. Historical Transcript Backfill: provenance, coverage ledger, utterance ledger, runs
            for ddl in (
                "ALTER TABLE verified_actions ADD COLUMN ingest_source TEXT NOT NULL DEFAULT 'live';",
                "ALTER TABLE verified_actions ADD COLUMN ingest_run_id TEXT;",
                "ALTER TABLE verified_actions ADD COLUMN source_key TEXT;",
                "ALTER TABLE planned_tasks ADD COLUMN ingest_source TEXT NOT NULL DEFAULT 'live';",
                "ALTER TABLE planned_tasks ADD COLUMN ingest_run_id TEXT;",
                "ALTER TABLE planned_tasks ADD COLUMN source_key TEXT;",
                "ALTER TABLE planned_tasks ADD COLUMN recovered INTEGER NOT NULL DEFAULT 0;",
                # Speaker identity (docs/next_steps/08_speaker_identity.md)
                "ALTER TABLE verified_actions ADD COLUMN speaker_json TEXT;",
                "ALTER TABLE planned_tasks ADD COLUMN speaker_json TEXT;",
                "ALTER TABLE session_dossiers ADD COLUMN ingest_source TEXT NOT NULL DEFAULT 'live';",
                "ALTER TABLE session_dossiers ADD COLUMN ingest_run_id TEXT;",
            ):
                try:
                    cursor.execute(ddl)
                except Exception:
                    pass
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_ingest ON session_dossiers (ingest_source, ingest_run_id);")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ingest_coverage (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    start_ts TEXT NOT NULL,
                    end_ts TEXT NOT NULL,
                    is_open INTEGER NOT NULL DEFAULT 0,
                    degraded INTEGER NOT NULL DEFAULT 0,
                    run_id TEXT,
                    utterances INTEGER NOT NULL DEFAULT 0,
                    errors INTEGER NOT NULL DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_coverage_time ON ingest_coverage (start_ts, end_ts);")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ingest_ledger (
                    source_key TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    bee_conversation_uuid TEXT,
                    bee_conversation_id INTEGER,
                    ts TEXT NOT NULL,
                    received_at TEXT,
                    text_norm TEXT,
                    text_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    categories_json TEXT,
                    run_id TEXT
                )
            """)
            try:
                # Utterance duration from Bee start/end (relative seconds): live spans for backfill dedup
                cursor.execute("ALTER TABLE ingest_ledger ADD COLUMN duration_ms INTEGER;")
            except Exception:
                pass
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_hash_time ON ingest_ledger (text_hash, received_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_ts ON ingest_ledger (ts);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_status ON ingest_ledger (status);")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bee_conversation_map (
                    uuid TEXT PRIMARY KEY,
                    id INTEGER,
                    first_seen_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backfill_runs (
                    id TEXT PRIMARY KEY,
                    trigger TEXT NOT NULL,
                    window_from TEXT NOT NULL,
                    window_to TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_backfill_runs_status ON backfill_runs (status, created_at DESC);")

            # 4. System Telemetry Table (Real Execution Latencies & Averages)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    model_id TEXT,
                    details_json TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_time ON system_telemetry (timestamp DESC);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_type ON system_telemetry (event_type);")

            # 5. FTS5 Virtual Tables (if supported by SQLite runtime)
            try:
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS fts_actions USING fts5(
                        action_type, raw_statement, content='verified_actions', content_rowid='rowid'
                    )
                """)
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS fts_social USING fts5(
                        person_name, company_or_role, content='social_contacts', content_rowid='rowid'
                    )
                """)
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS fts_briefings USING fts5(
                        topic_title, deep_dive_markdown, content='topic_briefings', content_rowid='rowid'
                    )
                """)
                self._has_fts = True
            except sqlite3.OperationalError:
                # Transparent fallback to LIKE matching if FTS5 is not compiled in SQLite
                self._has_fts = False

            conn.commit()

    # =========================================================================
    # Planned Tasks
    # =========================================================================
    def save_planned_task(self, task: PlannedTask) -> str:
        rec_id = task.id or str(uuid.uuid4())
        task.id = rec_id
        loc_str = json.dumps(task.location) if task.location else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO planned_tasks
                (id, title, domain, scheduled_time, recurrence, status, completed_at, verified_action_id, created_at,
                 origin, raw_statement, confidence, relative_time_anchor, session_id, location_json,
                 ingest_source, ingest_run_id, source_key, recovered, speaker_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec_id,
                task.title.strip(),
                task.domain,
                task.scheduled_time,
                task.recurrence,
                task.status,
                task.completed_at,
                task.verified_action_id,
                task.created_at,
                task.origin,
                task.raw_statement,
                task.confidence,
                task.relative_time_anchor,
                task.session_id,
                loc_str,
                task.ingest_source,
                task.ingest_run_id,
                task.source_key,
                1 if task.recovered else 0,
                rules.speaker_to_json(task.speaker),
            ))
            conn.commit()
        return rec_id

    _row_to_planned_task = staticmethod(rules.row_to_planned_task)

    def get_planned_task(self, task_id: str) -> Optional[PlannedTask]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute("SELECT * FROM planned_tasks WHERE id = ?", (task_id,)).fetchone()
            if row:
                return self._row_to_planned_task(row)
        return None

    def list_planned_tasks(
        self,
        status: Optional[str] = None,
        domain: Optional[str] = None,
        origin: Optional[str] = None,
        ingest_source: Optional[str] = None,
    ) -> List[PlannedTask]:
        sql = "SELECT * FROM planned_tasks WHERE 1=1"
        params = []
        if ingest_source:
            sql += " AND ingest_source = ?"
            params.append(ingest_source)
        if status:
            sql += " AND status = ?"
            params.append(status)
        if domain:
            sql += " AND domain = ?"
            params.append(domain)
        if origin:
            sql += " AND origin = ?"
            params.append(origin)
        sql += " ORDER BY scheduled_time ASC, created_at ASC"

        results = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql, params).fetchall()
            for r in rows:
                results.append(self._row_to_planned_task(r))
        return results

    def complete_planned_task(
        self, task_id: str, verified_action_id: str, completed_at: Optional[str] = None
    ) -> bool:
        comp_time = completed_at or datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE planned_tasks
                SET status = 'completed', completed_at = ?, verified_action_id = ?
                WHERE id = ?
            """, (comp_time, verified_action_id, task_id))
            conn.commit()
            return cursor.rowcount > 0

    def update_planned_task(self, task: PlannedTask) -> bool:
        if not task.id:
            return False
        loc_str = json.dumps(task.location) if task.location else None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE planned_tasks
                SET title = ?, domain = ?, scheduled_time = ?, recurrence = ?,
                    status = ?, completed_at = ?, verified_action_id = ?,
                    origin = ?, raw_statement = ?, confidence = ?,
                    relative_time_anchor = ?, session_id = ?, location_json = ?, speaker_json = ?
                WHERE id = ?
            """, (
                task.title.strip(),
                task.domain,
                task.scheduled_time,
                task.recurrence,
                task.status,
                task.completed_at,
                task.verified_action_id,
                task.origin,
                task.raw_statement,
                task.confidence,
                task.relative_time_anchor,
                task.session_id,
                loc_str,
                rules.speaker_to_json(task.speaker),
                task.id,
            ))
            conn.commit()
            return cursor.rowcount > 0

    def delete_planned_task(self, task_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM planned_tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0

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

        # Check each pending task for keyword overlap
        for task in pending_tasks:
            if rules.action_matches_task(action_text, task):
                self.complete_planned_task(
                    task_id=task.id,
                    verified_action_id=action.id,
                    completed_at=action.timestamp
                )
                task.status = "completed"
                task.completed_at = action.timestamp
                task.verified_action_id = action.id

                # Closed-Loop Reconciliation: fulfill linked commitment if task originated from a commitment
                if task.origin == "social_commitment":
                    with self._get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE social_commitments SET status = 'fulfilled' WHERE auto_scheduled_task_id = ?",
                            (task.id,)
                        )
                        conn.commit()

                return task

        # Also check open user commitments directly
        open_commitments = self.list_social_commitments(debtor="user", status="open")
        if historical:
            open_commitments = [
                c for c in open_commitments if historical_action_may_resolve(action.timestamp, c.created_at)
            ]
        for com in open_commitments:
            if rules.action_matches_commitment(action_text, com):
                self.update_social_commitment_status(com.id, "fulfilled")

        return None

    # =========================================================================
    # Action State
    # =========================================================================
    def save_action(self, action: VerifiedAction) -> str:
        rec_id = action.id or str(uuid.uuid4())
        action.id = rec_id

        # Auto-match with pending planned tasks if not already linked
        if not action.matched_task_id:
            resolved_task = self.match_and_resolve_task(action)
            if resolved_task:
                action.matched_task_id = resolved_task.id
        else:
            self.complete_planned_task(
                task_id=action.matched_task_id,
                verified_action_id=rec_id,
                completed_at=action.timestamp
            )

        loc_str = json.dumps(action.location) if action.location else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO verified_actions
                (id, action_type, domain, raw_statement, confidence, timestamp, is_revoked, matched_task_id, location_json,
                 session_id, ingest_source, ingest_run_id, source_key, speaker_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec_id,
                action.action_type.lower(),
                action.domain,
                action.raw_statement,
                action.confidence,
                action.timestamp,
                1 if action.is_revoked else 0,
                action.matched_task_id,
                loc_str,
                action.session_id,
                action.ingest_source,
                action.ingest_run_id,
                action.source_key,
                rules.speaker_to_json(action.speaker),
            ))
            if self._has_fts:
                cursor.execute("""
                    INSERT INTO fts_actions(rowid, action_type, raw_statement)
                    SELECT rowid, action_type, raw_statement FROM verified_actions WHERE id = ?
                """, (rec_id,))
            conn.commit()
        return rec_id


    _row_to_action = staticmethod(rules.row_to_action)

    def set_action_speaker(self, action_id: str, speaker: SpeakerAttribution, revoke: bool = False) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if revoke:
                cursor.execute("UPDATE verified_actions SET speaker_json = ?, is_revoked = 1 WHERE id = ?",
                               (rules.speaker_to_json(speaker), action_id))
            else:
                cursor.execute("UPDATE verified_actions SET speaker_json = ? WHERE id = ?",
                               (rules.speaker_to_json(speaker), action_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_verified_action(self, action_id: str) -> Optional[VerifiedAction]:
        with self._get_connection() as conn:
            row = conn.cursor().execute("SELECT * FROM verified_actions WHERE id = ?", (action_id,)).fetchone()
            return self._row_to_action(row) if row else None

    def get_action_status(
        self, action_query: str, target_date: Optional[str] = None
    ) -> Optional[VerifiedAction]:
        clean_query = f"%{action_query.strip().lower()}%"
        sql = """
            SELECT * FROM verified_actions 
            WHERE (id = ? OR action_type LIKE ? OR raw_statement LIKE ?)
              AND is_revoked = 0
        """
        params = [action_query.strip(), clean_query, clean_query]

        if target_date:
            sql += " AND timestamp LIKE ?"
            params.append(f"{target_date}%")

        sql += " ORDER BY timestamp DESC LIMIT 1"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute(sql, params).fetchone()
            if row:
                return self._row_to_action(row)
        return None

    def list_recent_actions(
        self, limit: int = 10, domain: Optional[str] = None, ingest_source: Optional[str] = None
    ) -> List[VerifiedAction]:
        sql = "SELECT * FROM verified_actions WHERE is_revoked = 0"
        params = []
        if domain and domain != "all":
            sql += " AND domain = ?"
            params.append(domain)
        if ingest_source:
            sql += " AND ingest_source = ?"
            params.append(ingest_source)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        results = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql, params).fetchall()
            for row in rows:
                results.append(self._row_to_action(row))
        return results

    def _fts_sync(self, conn: sqlite3.Connection, fts: str, columns: tuple, table: str, record_id: str,
                  remove: bool) -> None:
        """Keeps an external-content FTS5 mirror in step with one row (``remove``: before it changes)."""
        if not self._has_fts:
            return
        cols = ", ".join(columns)
        try:
            if remove:
                conn.execute(f"INSERT INTO {fts}({fts}, rowid, {cols}) SELECT 'delete', rowid, {cols} "
                             f"FROM {table} WHERE id = ?", (record_id,))
            else:
                conn.execute(f"INSERT INTO {fts}(rowid, {cols}) SELECT rowid, {cols} FROM {table} WHERE id = ?",
                             (record_id,))
        except sqlite3.OperationalError:
            pass

    _ACTION_FTS = ("action_type", "raw_statement")

    def update_action(self, action_id: str, changes: ActionChanges) -> Optional[VerifiedAction]:
        fields: Dict[str, Any] = {}
        if changes.action_type is not None:
            title = rules.normalize_action_type(changes.action_type)
            if not title:
                raise ValueError("action title cannot be empty")
            fields["action_type"] = title
        if changes.domain is not None:
            fields["domain"] = changes.domain
        with self._get_connection() as conn:
            row = conn.execute("SELECT id FROM verified_actions WHERE id = ? AND is_revoked = 0",
                               (action_id,)).fetchone()
            if not row:
                return None
            if fields:
                self._fts_sync(conn, "fts_actions", self._ACTION_FTS, "verified_actions", action_id, remove=True)
                conn.execute(f"UPDATE verified_actions SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                             (*fields.values(), action_id))
                self._fts_sync(conn, "fts_actions", self._ACTION_FTS, "verified_actions", action_id, remove=False)
                conn.commit()
        return self.get_verified_action(action_id)

    def revoke_action(self, action_id: str) -> Optional[RevokeResult]:
        action = self.get_verified_action(action_id)
        if action is None or action.is_revoked:
            return None
        reopened = None
        with self._get_connection() as conn:
            self._fts_sync(conn, "fts_actions", self._ACTION_FTS, "verified_actions", action_id, remove=True)
            cur = conn.execute("UPDATE verified_actions SET is_revoked = 1 WHERE id = ? AND is_revoked = 0",
                               (action_id,))
            if cur.rowcount == 0:
                return None
            if action.matched_task_id:
                cur = conn.execute(
                    "UPDATE planned_tasks SET status = 'pending', completed_at = NULL, verified_action_id = NULL "
                    "WHERE id = ? AND verified_action_id = ? AND status = 'completed'",
                    (action.matched_task_id, action_id),
                )
                if cur.rowcount:
                    reopened = action.matched_task_id
            conn.commit()
        action.is_revoked = True
        return RevokeResult(action=action, reopened_task_id=reopened)

    # =========================================================================
    # Social Recall
    # =========================================================================
    def save_social_contact(self, contact: SocialEntity) -> str:
        rec_id = contact.id
        if not rec_id and contact.person_name:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                existing = cursor.execute(
                    "SELECT id FROM social_contacts WHERE LOWER(person_name) = LOWER(?) LIMIT 1",
                    (contact.person_name.strip(),),
                ).fetchone()
                if existing:
                    rec_id = existing["id"]

        if not rec_id:
            rec_id = str(uuid.uuid4())
        contact.id = rec_id

        # Normalize commitments and persist structured bilateral commitments
        structured_commitments = contact.get_commitments_as_objects()
        unique_commitments: List[SocialCommitment] = []
        seen_keys = set()
        for com in structured_commitments:
            key = (com.description.strip().lower(), com.debtor)
            if key not in seen_keys:
                seen_keys.add(key)
                if not com.contact_name:
                    com.contact_name = contact.person_name
                unique_id = self.save_social_commitment(com)
                com.id = unique_id
                unique_commitments.append(com)

        # Retain json representation in contact record for fast retrieval/backward compatibility
        commitments_payload = [
            c.model_dump() if hasattr(c, "model_dump") else c
            for c in unique_commitments
        ]
        commitments_str = json.dumps(commitments_payload, ensure_ascii=False)
        topics_str = json.dumps(contact.key_topics, ensure_ascii=False)

        # Preserve existing web_profile_json and website_url if not provided in incoming contact
        web_profile_str = None
        website_url_val = getattr(contact, "website_url", None) or (
            getattr(contact.web_profile, "website_url", None) if getattr(contact, "web_profile", None) else None
        )
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            existing_row = cursor.execute(
                "SELECT web_profile_json, website_url FROM social_contacts WHERE id = ? OR LOWER(person_name) = LOWER(?)",
                (rec_id, contact.person_name),
            ).fetchone()
            if existing_row:
                if not getattr(contact, "web_profile", None) and "web_profile_json" in existing_row.keys() and existing_row["web_profile_json"]:
                    web_profile_str = existing_row["web_profile_json"]
                elif getattr(contact, "web_profile", None):
                    web_profile_str = contact.web_profile.model_dump_json()
                if not website_url_val and "website_url" in existing_row.keys() and existing_row["website_url"]:
                    website_url_val = existing_row["website_url"]
            elif getattr(contact, "web_profile", None):
                web_profile_str = contact.web_profile.model_dump_json()

        if website_url_val and hasattr(contact, "website_url"):
            contact.website_url = website_url_val

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO social_contacts
                (id, person_name, company_or_role, contact_info, commitments_json, key_topics_json, timestamp, web_profile_json, location_encountered, session_id, website_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec_id,
                contact.person_name,
                contact.company_or_role,
                contact.contact_info,
                commitments_str,
                topics_str,
                contact.timestamp,
                web_profile_str,
                contact.location_encountered,
                contact.session_id,
                website_url_val,
            ))
            if self._has_fts:
                cursor.execute("""
                    INSERT INTO fts_social(rowid, person_name, company_or_role)
                    SELECT rowid, person_name, company_or_role FROM social_contacts WHERE id = ?
                """, (rec_id,))
            conn.commit()
        return rec_id

    def get_social_contact(self, contact_id_or_name: str) -> Optional[SocialEntity]:
        target = contact_id_or_name.strip()
        sql = """
            SELECT * FROM social_contacts
            WHERE id = ? OR LOWER(person_name) = LOWER(?)
            ORDER BY timestamp DESC LIMIT 1
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute(sql, (target, target)).fetchone()
            if not row:
                return None
            return rules.row_to_contact(row, self.list_social_commitments(contact_name=row["person_name"]))

    def update_contact_web_profile(
        self, contact_id_or_name: str, profile: SocialWebProfile
    ) -> bool:
        target = contact_id_or_name.strip()
        profile_json = profile.model_dump_json()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            is_uuid = bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", target, re.IGNORECASE))
            if is_uuid:
                where_clause = "WHERE id = ?"
            else:
                where_clause = "WHERE LOWER(person_name) = LOWER(?)"

            if profile.website_url:
                cursor.execute(
                    f"""
                    UPDATE social_contacts
                    SET web_profile_json = ?, website_url = COALESCE(website_url, ?)
                    {where_clause}
                    """,
                    (profile_json, profile.website_url, target),
                )
            else:
                cursor.execute(
                    f"""
                    UPDATE social_contacts
                    SET web_profile_json = ?
                    {where_clause}
                    """,
                    (profile_json, target),
                )
            conn.commit()
            return cursor.rowcount > 0

    def search_social_contact(self, query: str) -> List[SocialEntity]:
        clean_query = f"%{query.strip().lower()}%"
        sql = """
            SELECT * FROM social_contacts
            WHERE LOWER(person_name) LIKE ? 
                OR LOWER(company_or_role) LIKE ?
                OR LOWER(key_topics_json) LIKE ?
            ORDER BY timestamp DESC
        """
        results = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql, (clean_query, clean_query, clean_query)).fetchall()
            for row in rows:
                results.append(rules.row_to_contact(row, self.list_social_commitments(contact_name=row["person_name"])))
        return results

    def save_social_commitment(self, commitment: SocialCommitment) -> str:
        rec_id = commitment.id
        # Always check for existing commitment for this person and description to avoid duplicates
        with self._get_connection() as conn:
            cursor = conn.cursor()
            existing = cursor.execute(
                """
                SELECT id, auto_scheduled_task_id, created_at FROM social_commitments
                WHERE LOWER(contact_name) = LOWER(?)
                  AND LOWER(description) = LOWER(?)
                  AND debtor = ?
                LIMIT 1
                """,
                (commitment.contact_name, commitment.description, commitment.debtor),
            ).fetchone()
            if existing:
                rec_id = existing["id"]
                if not commitment.auto_scheduled_task_id and existing["auto_scheduled_task_id"]:
                    commitment.auto_scheduled_task_id = existing["auto_scheduled_task_id"]
                if not commitment.created_at and existing["created_at"]:
                    commitment.created_at = existing["created_at"]

        if not rec_id:
            rec_id = str(uuid.uuid4())
        commitment.id = rec_id
        if not commitment.created_at:
            commitment.created_at = datetime.now().isoformat()

        # Milestone 1.3: Automatic Agenda Provisioning if debtor == 'user'
        if commitment.debtor == "user" and not commitment.auto_scheduled_task_id and commitment.status == "open":
            task_title = f"{commitment.description} (Promise to {commitment.contact_name})"
            planned_task = PlannedTask(
                title=task_title,
                domain="personal",
                scheduled_time=commitment.normalized_deadline or None,
                recurrence="none",
                status="pending",
                origin="social_commitment",
                raw_statement=commitment.description,
                confidence=1.0,
            )
            task_id = self.save_planned_task(planned_task)
            commitment.auto_scheduled_task_id = task_id

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO social_commitments
                (id, contact_name, debtor, description, due_date_raw, normalized_deadline, status, auto_scheduled_task_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec_id,
                commitment.contact_name,
                commitment.debtor,
                commitment.description,
                commitment.due_date_raw,
                commitment.normalized_deadline,
                commitment.status,
                commitment.auto_scheduled_task_id,
                commitment.created_at,
            ))
            conn.commit()
        return rec_id

    def get_social_commitment(self, commitment_id: str) -> Optional[SocialCommitment]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute("SELECT * FROM social_commitments WHERE id = ?", (commitment_id,)).fetchone()
            if row:
                return rules.row_to_commitment(row)
        return None

    def list_social_commitments(
        self,
        contact_name: Optional[str] = None,
        debtor: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SocialCommitment]:
        sql = "SELECT * FROM social_commitments WHERE 1=1"
        params = []
        if contact_name:
            sql += " AND LOWER(contact_name) = LOWER(?)"
            params.append(contact_name.strip())
        if debtor:
            sql += " AND debtor = ?"
            params.append(debtor)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        results = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql, params).fetchall()
            for r in rows:
                results.append(rules.row_to_commitment(r))
        return results

    def update_social_commitment_status(
        self, commitment_id: str, status: str
    ) -> bool:
        commitment = self.get_social_commitment(commitment_id)
        if not commitment:
            return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE social_commitments SET status = ? WHERE id = ?",
                (status, commitment_id),
            )
            conn.commit()

        # If fulfilling, complete linked planned task if one exists
        if status == "fulfilled" and commitment.auto_scheduled_task_id:
            self.complete_planned_task(
                task_id=commitment.auto_scheduled_task_id,
                verified_action_id="commitment_fulfilled",
                completed_at=datetime.now().isoformat(),
            )
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

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM social_commitments WHERE id = ?", (commitment_id,))
            conn.commit()

        # If it had an auto scheduled task, also clean it up
        if commitment.auto_scheduled_task_id:
            try:
                self.delete_planned_task(commitment.auto_scheduled_task_id)
            except Exception:
                pass

        return True

    _SOCIAL_FTS = ("person_name", "company_or_role")

    def update_social_contact(self, contact_id: str, changes: ContactChanges) -> Optional[ContactUpdate]:
        data = changes.model_dump(exclude_unset=True)
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM social_contacts WHERE id = ?", (contact_id,)).fetchone()
            if not row:
                return None
            old_name = row["person_name"]
            new_name = data.get("person_name") or old_name
            renamed = rules.contact_name_key(new_name) != rules.contact_name_key(old_name)
            if renamed and conn.execute(
                "SELECT 1 FROM social_contacts WHERE LOWER(person_name) = LOWER(?) AND id <> ? LIMIT 1",
                (new_name.strip(), contact_id),
            ).fetchone():
                raise UniqueConflict("Another contact already has this name")
            anchors_changed = any(
                field in data and rules.contact_name_key(data[field]) != rules.contact_name_key(row[field])
                for field in rules.CONTACT_ANCHORS
            )
            sets: Dict[str, Any] = {}
            for field in ("person_name", "company_or_role", "contact_info", "website_url", "location_encountered"):
                if field in data:
                    sets[field] = (data[field] or "").strip() or None
            if "key_topics" in data:
                sets["key_topics_json"] = json.dumps(data["key_topics"] or [], ensure_ascii=False)
            if anchors_changed:
                sets["web_profile_json"] = None  # the profile described the person the old anchors found
                if "website_url" not in data:
                    sets["website_url"] = None
            if sets:
                self._fts_sync(conn, "fts_social", self._SOCIAL_FTS, "social_contacts", contact_id, remove=True)
                conn.execute(f"UPDATE social_contacts SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?",
                             (*sets.values(), contact_id))
                if renamed:
                    conn.execute("UPDATE social_commitments SET contact_name = ? WHERE LOWER(contact_name) = LOWER(?)",
                                 (new_name, old_name))
                self._fts_sync(conn, "fts_social", self._SOCIAL_FTS, "social_contacts", contact_id, remove=False)
                conn.commit()
        if renamed:
            payload = [c.model_dump() for c in self.list_social_commitments(contact_name=new_name, limit=10_000)]
            with self._get_connection() as conn:
                conn.execute("UPDATE social_contacts SET commitments_json = ? WHERE id = ?",
                             (json.dumps(payload, ensure_ascii=False), contact_id))
                conn.commit()
        contact = self.get_social_contact(contact_id)
        return ContactUpdate(contact=contact, anchors_changed=anchors_changed,
                             renamed_from=old_name if renamed else None)

    def delete_social_contact(self, contact_id: str) -> Optional[ContactDeletion]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM social_contacts WHERE id = ?", (contact_id,)).fetchone()
            if not row:
                return None
            shared = conn.execute(
                "SELECT 1 FROM social_contacts WHERE LOWER(person_name) = LOWER(?) AND id <> ? LIMIT 1",
                (row["person_name"], contact_id),
            ).fetchone()
        # Commitments are keyed by name: keep them when another contact still has that name
        commitments = [] if shared else rules.contact_cascade(self, row["person_name"])
        tasks = 0
        for com in commitments:
            if com.auto_scheduled_task_id and self.get_planned_task(com.auto_scheduled_task_id):
                tasks += 1
            self.delete_social_commitment(com.id)
        with self._get_connection() as conn:
            self._fts_sync(conn, "fts_social", self._SOCIAL_FTS, "social_contacts", contact_id, remove=True)
            conn.execute("DELETE FROM social_contacts WHERE id = ?", (contact_id,))
            conn.commit()
        return ContactDeletion(contact_id=contact_id, name=row["person_name"], session_id=row["session_id"],
                               commitments_deleted=len(commitments), tasks_deleted=tasks)

    # =========================================================================
    # Topic Intelligence
    # =========================================================================
    def save_topic_briefing(self, briefing: BriefingReport) -> str:
        rec_id = briefing.id or str(uuid.uuid4())
        briefing.id = rec_id

        exec_summary_str = json.dumps(briefing.executive_summary, ensure_ascii=False)
        sources_str = json.dumps(briefing.web_sources, ensure_ascii=False)
        items_str = json.dumps(briefing.action_items, ensure_ascii=False)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO topic_briefings
                (id, topic_title, context_type, executive_summary_json, explanatory_synthesis, deep_dive_markdown,
                 web_sources_json, action_items_json, created_at, session_id, segment_id, kind)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec_id,
                briefing.topic_title,
                briefing.context_type,
                exec_summary_str,
                briefing.explanatory_synthesis or "",
                briefing.deep_dive_markdown,
                sources_str,
                items_str,
                briefing.created_at,
                briefing.session_id,
                briefing.segment_id,
                briefing.kind,
            ))
            if self._has_fts:
                cursor.execute("""
                    INSERT INTO fts_briefings(rowid, topic_title, deep_dive_markdown)
                    SELECT rowid, topic_title, deep_dive_markdown FROM topic_briefings WHERE id = ?
                """, (rec_id,))
            conn.commit()
        return rec_id

    _row_to_briefing = staticmethod(rules.row_to_briefing)

    def get_topic_briefing(self, query: Optional[str] = None) -> Optional[BriefingReport]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if query and query.strip():
                clean_target = query.strip()
                clean_query = f"%{clean_target.lower()}%"
                sql = """
                    SELECT * FROM topic_briefings
                    WHERE id = ? OR LOWER(topic_title) LIKE ? OR LOWER(deep_dive_markdown) LIKE ? OR LOWER(COALESCE(explanatory_synthesis, '')) LIKE ?
                    ORDER BY (id = ?) DESC, created_at DESC LIMIT 1
                """
                row = cursor.execute(
                    sql, (clean_target, clean_query, clean_query, clean_query, clean_target)
                ).fetchone()
            else:
                sql = "SELECT * FROM topic_briefings ORDER BY created_at DESC LIMIT 1"
                row = cursor.execute(sql).fetchone()

            if row:
                return self._row_to_briefing(row)
        return None

    def list_topic_briefings(
        self, limit: int = 10, kind: Optional[str] = None, session_id: Optional[str] = None
    ) -> List[BriefingReport]:
        sql = "SELECT * FROM topic_briefings "
        clauses: List[str] = []
        params: List[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._get_connection() as conn:
            rows = conn.cursor().execute(sql, params).fetchall()
            return [self._row_to_briefing(row) for row in rows]

    def list_briefings_for_session(self, session_id: str) -> List[BriefingReport]:
        with self._get_connection() as conn:
            rows = conn.cursor().execute(
                "SELECT * FROM topic_briefings WHERE session_id = ? ORDER BY created_at ASC", (session_id,)
            ).fetchall()
            return [self._row_to_briefing(row) for row in rows]

    def patch_utterance_speaker(
        self, chunk_id: str, speaker_id: str, speaker_role: Optional[str] = None
    ) -> bool:
        """Records a late speaker identity (Bee `tagged-utterance`) for an utterance.

        Only the diarization table is written: actions and tasks have no speaker column, and their
        `session_id` / `matched_task_id` must never be overwritten with a speaker label.
        """
        with self._get_connection() as conn:
            conn.cursor().execute(
                "INSERT OR REPLACE INTO utterance_diarization (chunk_id, speaker_id, speaker_role, updated_at) VALUES (?, ?, ?, ?)",
                (chunk_id, speaker_id, speaker_role or "unknown", datetime.now(timezone.utc).isoformat())
            )
            conn.commit()
        return True

    # =========================================================================
    # Macro Session & Micro-Event Decoupling (Milestone 3.2)
    # =========================================================================
    def save_session_dossier(self, dossier: SessionDossier) -> str:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Chunks logged in session_chunks are the source of truth; the legacy JSON blob is only
            # written for sessions that never used the per-chunk log.
            has_chunk_log = cursor.execute(
                "SELECT 1 FROM session_chunks WHERE session_id = ? LIMIT 1", (dossier.session_id,)
            ).fetchone() is not None
            chunks_str = None if has_chunk_log else json.dumps(dossier.transcript_chunks, ensure_ascii=False)
            columns = rules.dossier_columns(dossier, chunks_str)
            cursor.execute(
                f"INSERT OR REPLACE INTO session_dossiers ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                tuple(columns.values()),
            )
            conn.commit()
        return dossier.session_id

    def _row_to_session_dossier(
        self, row: sqlite3.Row, cursor: sqlite3.Cursor, max_chunks: int = 200, include_chunks: bool = True
    ) -> SessionDossier:
        # Prefer the per-chunk log; fall back to the legacy JSON blob
        chunks: List[str] = []
        if include_chunks:
            chunk_rows = cursor.execute(
                "SELECT text FROM (SELECT text, ts, rowid FROM session_chunks WHERE session_id = ? "
                "ORDER BY ts DESC, rowid DESC LIMIT ?) ORDER BY ts ASC, rowid ASC",
                (row["session_id"], max_chunks),
            ).fetchall()
            chunks = [r["text"] for r in chunk_rows]
        briefing_report = self.get_topic_briefing(row["final_briefing_id"]) if row["final_briefing_id"] else None
        return rules.row_to_dossier(row, chunks, briefing_report)

    def get_session_dossier(
        self, session_id: Optional[str] = None, include_chunks: bool = True
    ) -> Optional[SessionDossier]:
        sql = "SELECT * FROM session_dossiers "
        params = []
        if session_id:
            sql += "WHERE session_id = ? LIMIT 1"
            params.append(session_id)
        else:
            sql += "ORDER BY last_updated_at DESC LIMIT 1"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute(sql, params).fetchone()
            if not row:
                return None
            return self._row_to_session_dossier(row, cursor, include_chunks=include_chunks)

    def list_session_dossiers(
        self,
        status: Optional[str] = None,
        limit: int = 10,
        ingest_source: Optional[str] = None,
        ingest_run_id: Optional[str] = None,
    ) -> List[SessionDossier]:
        sql = "SELECT * FROM session_dossiers WHERE 1=1 "
        params: List[Any] = []
        if status:
            sql += "AND status = ? "
            params.append(status)
        if ingest_source:
            sql += "AND ingest_source = ? "
            params.append(ingest_source)
        if ingest_run_id:
            sql += "AND ingest_run_id = ? "
            params.append(ingest_run_id)
        sql += "ORDER BY start_time DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql, params).fetchall()
            return [self._row_to_session_dossier(row, cursor) for row in rows]

    def get_open_event(
        self, ingest_source: str = "live", run_id: Optional[str] = None
    ) -> Optional[SessionDossier]:
        """Returns the most recent engine-managed event that is still active or paused.

        Scoped by ingestion path so the live engine never adopts a backfill event (and vice versa).
        """
        sql = (
            "SELECT * FROM session_dossiers WHERE status IN ('active', 'paused') "
            "AND segments_json IS NOT NULL AND COALESCE(ingest_source, 'live') = ? "
        )
        params: List[Any] = [ingest_source]
        if run_id:
            sql += "AND ingest_run_id = ? "
            params.append(run_id)
        sql += "ORDER BY last_updated_at DESC LIMIT 1"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute(sql, params).fetchone()
            if not row:
                return None
            return self._row_to_session_dossier(row, cursor)

    def list_events_pending_final(
        self, limit: int = 20, ingest_source: Optional[str] = None, run_id: Optional[str] = None
    ) -> List[SessionDossier]:
        """Returns concluded events whose final briefing has not been produced yet."""
        sql = (
            "SELECT * FROM session_dossiers WHERE status = 'concluded' "
            "AND final_status IN ('pending', 'synthesizing') "
        )
        params: List[Any] = []
        if ingest_source:
            sql += "AND COALESCE(ingest_source, 'live') = ? "
            params.append(ingest_source)
        if run_id:
            sql += "AND ingest_run_id = ? "
            params.append(run_id)
        sql += "ORDER BY last_updated_at ASC LIMIT ?"
        params.append(limit)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql, params).fetchall()
            return [self._row_to_session_dossier(row, cursor) for row in rows]

    def append_session_chunk(
        self,
        chunk: UtteranceChunk,
        session_id: str,
        segment_id: Optional[str] = None,
        on_topic: bool = False,
    ) -> None:
        """Appends one utterance to the per-chunk event log (idempotent on chunk_id)."""
        with self._get_connection() as conn:
            conn.cursor().execute("""
                INSERT OR REPLACE INTO session_chunks
                (chunk_id, session_id, segment_id, conversation_uuid, ts, text, word_count,
                 speaker_id, speaker_role, categories_json, on_topic, location_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk.chunk_id,
                session_id,
                segment_id,
                chunk.conversation_uuid,
                chunk.timestamp,
                chunk.text,
                len(chunk.text.split()),
                chunk.speaker_id,
                chunk.speaker_role,
                json.dumps(chunk.categories, ensure_ascii=False),
                1 if on_topic else 0,
                json.dumps(chunk.location, ensure_ascii=False) if chunk.location else None,
            ))
            conn.commit()

    def list_session_chunks(
        self,
        session_id: str,
        segment_id: Optional[str] = None,
        in_segments_only: bool = False,
        limit: Optional[int] = None,
    ) -> List[UtteranceChunk]:
        """Lists logged chunks of an event in chronological order."""
        sql = "SELECT * FROM session_chunks WHERE session_id = ? "
        params: List[Any] = [session_id]
        if segment_id:
            sql += "AND segment_id = ? "
            params.append(segment_id)
        elif in_segments_only:
            sql += "AND segment_id IS NOT NULL "
        sql += "ORDER BY ts ASC, rowid ASC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self._get_connection() as conn:
            rows = conn.cursor().execute(sql, params).fetchall()
        result: List[UtteranceChunk] = []
        for row in rows:
            result.append(UtteranceChunk(
                chunk_id=row["chunk_id"],
                conversation_uuid=row["conversation_uuid"] or "default_session",
                text=row["text"],
                speaker_id=row["speaker_id"],
                speaker_role=row["speaker_role"] or "unknown",
                timestamp=row["ts"],
                categories=json.loads(row["categories_json"]) if row["categories_json"] else [],
                location=json.loads(row["location_json"]) if row["location_json"] else None,
            ))
        return result

    def get_chunk_segments(self, session_id: str) -> Dict[str, Optional[str]]:
        """chunk_id -> segment_id (None for chunks logged outside any segment, e.g. during a pause)."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT chunk_id, segment_id FROM session_chunks WHERE session_id = ?", (session_id,)
            ).fetchall()
        return {row["chunk_id"]: row["segment_id"] for row in rows}

    def delete_session_dossier(self, session_id: str) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM session_dossiers WHERE session_id = ?", (session_id,))
            conn.commit()
            return cur.rowcount > 0

    def delete_topic_briefing(self, briefing_id: str) -> bool:
        with self._get_connection() as conn:
            if self._has_fts:
                try:
                    conn.execute(
                        "INSERT INTO fts_briefings(fts_briefings, rowid, topic_title, deep_dive_markdown) "
                        "SELECT 'delete', rowid, topic_title, deep_dive_markdown FROM topic_briefings WHERE id = ?",
                        (briefing_id,),
                    )
                except sqlite3.OperationalError:
                    pass
            cur = conn.execute("DELETE FROM topic_briefings WHERE id = ?", (briefing_id,))
            conn.commit()
            return cur.rowcount > 0

    def reassign_briefings(self, briefing_ids: List[str], session_id: str) -> None:
        if not briefing_ids:
            return
        placeholders = ",".join("?" for _ in briefing_ids)
        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE topic_briefings SET session_id = ? WHERE id IN ({placeholders})",
                [session_id, *briefing_ids],
            )
            conn.commit()

    def get_cached_search(self, query_norm: str, max_age_seconds: int) -> Optional[dict]:
        """Returns {'provider', 'results'} for a cached web search younger than max_age_seconds."""
        with self._get_connection() as conn:
            row = conn.cursor().execute(
                "SELECT provider, results_json, fetched_at FROM web_search_cache WHERE query_norm = ?",
                (query_norm,),
            ).fetchone()
        if not row:
            return None
        try:
            age = (datetime.now() - datetime.fromisoformat(row["fetched_at"])).total_seconds()
        except ValueError:
            return None
        if age > max_age_seconds:
            return None
        return {"provider": row["provider"], "results": json.loads(row["results_json"])}

    def put_cached_search(self, query_norm: str, provider: str, results: List[dict]) -> None:
        with self._get_connection() as conn:
            conn.cursor().execute(
                "INSERT OR REPLACE INTO web_search_cache (query_norm, provider, results_json, fetched_at) "
                "VALUES (?, ?, ?, ?)",
                (query_norm, provider, json.dumps(results, ensure_ascii=False), datetime.now().isoformat()),
            )
            conn.commit()

    def assign_chunks(
        self,
        chunk_ids: List[str],
        session_id: str,
        segment_id: Optional[str],
        on_topic: Optional[bool] = None,
    ) -> None:
        """Moves logged chunks to an event/segment (resume after pause, split on topic change)."""
        if not chunk_ids:
            return
        placeholders = ",".join("?" for _ in chunk_ids)
        sql = f"UPDATE session_chunks SET session_id = ?, segment_id = ?"
        params: List[Any] = [session_id, segment_id]
        if on_topic is not None:
            sql += ", on_topic = ?"
            params.append(1 if on_topic else 0)
        sql += f" WHERE chunk_id IN ({placeholders})"
        params.extend(chunk_ids)
        with self._get_connection() as conn:
            conn.execute(sql, params)
            conn.commit()

    def append_chunk_to_session(
        self, session_id: str, chunk_text: str, location: Optional[dict] = None
    ) -> SessionDossier:
        dossier = self.get_session_dossier(session_id)
        now_iso = datetime.now().isoformat()
        if not dossier:
            dossier = SessionDossier(
                session_id=session_id,
                title=f"Session {session_id[:8]}",
                domain="meeting",
                start_time=now_iso,
                last_updated_at=now_iso,
                status="active",
                location=location,
                transcript_chunks=[chunk_text] if chunk_text and chunk_text.strip() else [],
            )
        elif dossier.status == "concluded":
            # Never silently grow a concluded session: callers must open a new one
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

    def link_micro_event_to_session(
        self, session_id: str, event_ref: Any
    ) -> bool:
        if isinstance(event_ref, dict):
            event_ref = MicroEventRef(**event_ref)
        elif not isinstance(event_ref, MicroEventRef):
            return False

        dossier = self.get_session_dossier(session_id)
        now_iso = datetime.now().isoformat()
        if not dossier:
            dossier = SessionDossier(
                session_id=session_id,
                title=f"Session {session_id[:8]}",
                domain="meeting",
                start_time=now_iso,
                last_updated_at=now_iso,
                status="active",
                linked_micro_events=[event_ref],
            )
        else:
            exists = any(
                e.record_id == event_ref.record_id and e.event_type == event_ref.event_type
                for e in dossier.linked_micro_events
            )
            if not exists:
                dossier.linked_micro_events.append(event_ref)
            # Update only the micro-event columns: the Deep Topic Event Engine owns the lifecycle
            # fields and may be writing them concurrently from another thread.
            events_payload = [e.model_dump() for e in dossier.linked_micro_events]
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE session_dossiers SET linked_micro_events_json = ?, last_updated_at = ? "
                    "WHERE session_id = ?",
                    (json.dumps(events_payload, ensure_ascii=False), now_iso, session_id),
                )
                conn.commit()
            return True

        self.save_session_dossier(dossier)
        return True

    def unlink_micro_event(self, session_id: str, event_type: str, record_id: str) -> bool:
        with self._get_connection() as conn:
            row = conn.execute("SELECT linked_micro_events_json FROM session_dossiers WHERE session_id = ?",
                               (session_id,)).fetchone()
            if not row:
                return False
            refs = json.loads(row["linked_micro_events_json"] or "[]")
            kept = [r for r in refs if not (r.get("event_type") == event_type and r.get("record_id") == record_id)]
            if len(kept) == len(refs):
                return False
            conn.execute("UPDATE session_dossiers SET linked_micro_events_json = ? WHERE session_id = ?",
                         (json.dumps(kept, ensure_ascii=False), session_id))
            conn.commit()
        return True

    def delete_event(self, session_id: str) -> Optional[EventDeletion]:
        dossier = self.get_session_dossier(session_id, include_chunks=False)
        if dossier is None:
            return None
        briefing_ids = {b.id for b in self.list_briefings_for_session(session_id)}
        if dossier.final_briefing_id:
            briefing_ids.add(dossier.final_briefing_id)
        briefings = sum(1 for bid in briefing_ids if bid and self.delete_topic_briefing(bid))
        with self._get_connection() as conn:
            conn.execute("DELETE FROM utterance_diarization WHERE chunk_id IN "
                         "(SELECT chunk_id FROM session_chunks WHERE session_id = ?)", (session_id,))
            chunks = conn.execute("DELETE FROM session_chunks WHERE session_id = ?", (session_id,)).rowcount
            conn.execute("DELETE FROM session_dossiers WHERE session_id = ?", (session_id,))
            conn.commit()
        return EventDeletion(session_id=session_id, title=dossier.title, briefings_deleted=briefings,
                             chunks_deleted=chunks)

    def conclude_session_dossier(
        self, session_id: str, briefing_report_id: Optional[str] = None
    ) -> Optional[SessionDossier]:
        dossier = self.get_session_dossier(session_id)
        if not dossier:
            return None

        now_iso = datetime.now().isoformat()
        dossier.status = "concluded"
        dossier.concluded_at = now_iso
        dossier.last_updated_at = now_iso
        if briefing_report_id:
            dossier.final_briefing_id = briefing_report_id
            dossier.briefing_report = self.get_topic_briefing(briefing_report_id)

        self.save_session_dossier(dossier)
        return dossier

    def record_latency(
        self,
        event_type: str,
        latency_ms: float,
        model_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Records an execution latency sample into system_telemetry."""
        details_str = json.dumps(details or {}, ensure_ascii=False)
        ts = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO system_telemetry (timestamp, event_type, latency_ms, model_id, details_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (ts, event_type, float(latency_ms), model_id, details_str),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to record system telemetry: {e}")

    def get_latency_metrics(
        self, event_type: Optional[str] = None, limit: int = 50
    ) -> dict:
        """Retrieves aggregated execution latency metrics (average, latest, min, max, count)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if event_type:
                    rows = cursor.execute(
                        """
                        SELECT latency_ms FROM system_telemetry
                        WHERE event_type = ?
                        ORDER BY timestamp DESC LIMIT ?
                        """,
                        (event_type, limit),
                    ).fetchall()
                else:
                    # Backfill runs are excluded so they do not skew the live rolling average
                    rows = cursor.execute(
                        """
                        SELECT latency_ms FROM system_telemetry
                        WHERE event_type NOT LIKE 'backfill%'
                        ORDER BY timestamp DESC LIMIT ?
                        """,
                        (limit,),
                    ).fetchall()

                return rules.latency_summary([float(r["latency_ms"]) for r in rows])
        except Exception as e:
            logger.warning(f"Failed to query latency metrics: {e}")
            return rules.latency_summary([])

    # =========================================================================
    # Historical Transcript Backfill (docs/next_steps/historical_backfill/)
    # =========================================================================
    _row_to_coverage = staticmethod(rules.row_to_coverage)

    def save_coverage_interval(self, interval: CoverageInterval) -> str:
        with self._get_connection() as conn:
            conn.cursor().execute("""
                INSERT OR REPLACE INTO ingest_coverage
                (id, source, start_ts, end_ts, is_open, degraded, run_id, utterances, errors)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                interval.id, interval.source, interval.start, interval.end, 1 if interval.is_open else 0,
                1 if interval.degraded else 0, interval.run_id, interval.utterances, interval.errors,
            ))
            conn.commit()
        return interval.id

    def list_coverage(
        self, start: Optional[str] = None, end: Optional[str] = None, source: Optional[str] = None
    ) -> List[CoverageInterval]:
        """Coverage intervals overlapping [start, end], oldest first."""
        sql = "SELECT * FROM ingest_coverage WHERE 1=1"
        params: List[Any] = []
        if start:
            sql += " AND end_ts >= ?"
            params.append(start)
        if end:
            sql += " AND start_ts <= ?"
            params.append(end)
        if source:
            sql += " AND source = ?"
            params.append(source)
        sql += " ORDER BY start_ts ASC"
        with self._get_connection() as conn:
            rows = conn.cursor().execute(sql, params).fetchall()
            return [self._row_to_coverage(r) for r in rows]

    def close_open_coverage_intervals(self, source: str = "live") -> int:
        """Marks intervals left open by a crash as closed (their end is the last persisted flush)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE ingest_coverage SET is_open = 0 WHERE is_open = 1 AND source = ?", (source,))
            conn.commit()
            return cursor.rowcount

    def last_coverage_end(self, source: Optional[str] = None) -> Optional[str]:
        sql = "SELECT MAX(end_ts) AS last_end FROM ingest_coverage"
        params: List[Any] = []
        if source:
            sql += " WHERE source = ?"
            params.append(source)
        with self._get_connection() as conn:
            row = conn.cursor().execute(sql, params).fetchone()
            return row["last_end"] if row else None

    def record_ingested_utterance(self, entry: Dict[str, Any]) -> None:
        """Upserts one utterance into the ingest ledger (keyed on source_key)."""
        with self._get_connection() as conn:
            conn.cursor().execute("""
                INSERT OR REPLACE INTO ingest_ledger
                (source_key, source, bee_conversation_uuid, bee_conversation_id, ts, received_at,
                 text_norm, text_hash, status, categories_json, run_id, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry["source_key"],
                entry.get("source", "live"),
                entry.get("bee_conversation_uuid"),
                entry.get("bee_conversation_id"),
                entry["ts"],
                entry.get("received_at"),
                entry.get("text_norm"),
                entry["text_hash"],
                entry.get("status", "screened_noop"),
                json.dumps(entry.get("categories") or [], ensure_ascii=False),
                entry.get("run_id"),
                entry.get("duration_ms"),
            ))
            conn.commit()

    _row_to_ledger = staticmethod(rules.row_to_ledger)

    def get_ledger_entry(self, source_key: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.cursor().execute(
                "SELECT * FROM ingest_ledger WHERE source_key = ?", (source_key,)
            ).fetchone()
            return self._row_to_ledger(row) if row else None

    def list_ledger_entries(
        self,
        t_from: str,
        t_to: str,
        source: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Ledger rows whose receive time (live) or spoken time falls within [t_from, t_to]."""
        sql = "SELECT * FROM ingest_ledger WHERE COALESCE(received_at, ts) >= ? AND COALESCE(received_at, ts) <= ?"
        params: List[Any] = [t_from, t_to]
        if source:
            sql += " AND source = ?"
            params.append(source)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY COALESCE(received_at, ts) ASC"
        with self._get_connection() as conn:
            rows = conn.cursor().execute(sql, params).fetchall()
            return [self._row_to_ledger(r) for r in rows]

    def purge_ingest_ledger(self, before: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ingest_ledger WHERE COALESCE(received_at, ts) < ?", (before,))
            conn.commit()
            return cursor.rowcount

    def map_bee_conversation(self, conv_uuid: str, conv_id: Optional[int]) -> None:
        if not conv_uuid:
            return
        with self._get_connection() as conn:
            conn.cursor().execute("""
                INSERT INTO bee_conversation_map (uuid, id, first_seen_at) VALUES (?, ?, ?)
                ON CONFLICT(uuid) DO UPDATE SET id = COALESCE(excluded.id, bee_conversation_map.id)
            """, (conv_uuid, conv_id, datetime.now().isoformat()))
            conn.commit()

    def get_bee_conversation_uuid(self, conv_id: int) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.cursor().execute(
                "SELECT uuid FROM bee_conversation_map WHERE id = ? LIMIT 1", (conv_id,)
            ).fetchone()
            return row["uuid"] if row else None

    def save_backfill_run(self, run: BackfillRun) -> str:
        with self._get_connection() as conn:
            conn.cursor().execute("""
                INSERT OR REPLACE INTO backfill_runs (id, trigger, window_from, window_to, status, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                run.id, run.trigger, run.window_from, run.window_to, run.status,
                run.model_dump_json(), run.created_at,
            ))
            conn.commit()
        return run.id

    def get_backfill_run(self, run_id: str) -> Optional[BackfillRun]:
        with self._get_connection() as conn:
            row = conn.cursor().execute(
                "SELECT payload_json FROM backfill_runs WHERE id = ?", (run_id,)
            ).fetchone()
            return BackfillRun.model_validate_json(row["payload_json"]) if row else None

    def list_backfill_runs(
        self, statuses: Optional[List[str]] = None, limit: int = 20
    ) -> List[BackfillRun]:
        sql = "SELECT payload_json FROM backfill_runs"
        params: List[Any] = []
        if statuses:
            sql += f" WHERE status IN ({','.join('?' for _ in statuses)})"
            params.extend(statuses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._get_connection() as conn:
            rows = conn.cursor().execute(sql, params).fetchall()
            return [BackfillRun.model_validate_json(r["payload_json"]) for r in rows]

    def purge_ingestion_history(self) -> None:
        """GDPR erasure of the backfill bookkeeping (coverage, ledger text, conversation map, runs)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for table in ("ingest_coverage", "ingest_ledger", "bee_conversation_map", "backfill_runs"):
                cursor.execute(f"DELETE FROM {table}")
            conn.commit()

    def export_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """GDPR Art. 15 / 20 export: all rows of every data table (FTS index tables are skipped)."""
        out: Dict[str, List[Dict[str, Any]]] = {}
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            names = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()]
            fts = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND sql LIKE '%VIRTUAL TABLE%'"
            ).fetchall()}
            skip = {n for n in names if any(n == f or n.startswith(f + "_") for f in fts)}
            for name in names:
                if name in skip:
                    continue
                rows = conn.execute(f'SELECT * FROM "{name}"').fetchall()
                out[name] = [{k: row[k] for k in row.keys()} for row in rows]
        return out

    def delete_all_data(self) -> None:
        """Erases every row of this store (GDPR erasure, ``reset_db.py``); the schema stays."""
        with self._get_connection() as conn:
            names = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "AND sql NOT LIKE '%VIRTUAL TABLE%'"
            ).fetchall()]
            for name in names:
                if any(name.startswith(f"{fts}_") for fts in ("fts_actions", "fts_social", "fts_briefings")):
                    continue
                conn.execute(f'DELETE FROM "{name}"')
            if self._has_fts:
                for fts in ("fts_actions", "fts_social", "fts_briefings"):
                    conn.execute(f"INSERT INTO {fts}({fts}) VALUES ('delete-all')")
            conn.commit()

    def close(self) -> None:
        """Close connection pools or resources if applicable."""
        pass


from datetime import datetime, timezone
import json
import re
import sqlite3
import uuid
from typing import Any, List, Optional, Union

from src.core.schemas import (
    BriefingReport,
    MicroEventRef,
    PlannedTask,
    SessionDossier,
    SocialCommitment,
    SocialEntity,
    SocialWebProfile,
    VerifiedAction,
)
from src.core.storage.base import AbstractContextStore


class SQLiteContextStore(AbstractContextStore):
    """Local SQLite context database with FTS5 indexing."""

    def __init__(self, db_path: str = "examen.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
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

            # 4. FTS5 Virtual Tables (if supported by SQLite runtime)
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
                 origin, raw_statement, confidence, relative_time_anchor, session_id, location_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ))
            conn.commit()
        return rec_id

    def get_planned_task(self, task_id: str) -> Optional[PlannedTask]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute("SELECT * FROM planned_tasks WHERE id = ?", (task_id,)).fetchone()
            if row:
                loc = json.loads(row["location_json"]) if ("location_json" in row.keys() and row["location_json"]) else None
                return PlannedTask(
                    id=row["id"],
                    title=row["title"],
                    domain=row["domain"],
                    scheduled_time=row["scheduled_time"],
                    recurrence=row["recurrence"],
                    status=row["status"],
                    completed_at=row["completed_at"],
                    verified_action_id=row["verified_action_id"],
                    created_at=row["created_at"],
                    origin=row["origin"] if ("origin" in row.keys() and row["origin"]) else "manual",
                    raw_statement=row["raw_statement"] if "raw_statement" in row.keys() else None,
                    confidence=row["confidence"] if ("confidence" in row.keys() and row["confidence"] is not None) else 1.0,
                    relative_time_anchor=row["relative_time_anchor"] if "relative_time_anchor" in row.keys() else None,
                    session_id=row["session_id"] if "session_id" in row.keys() else None,
                    location=loc,
                )
        return None

    def list_planned_tasks(
        self, status: Optional[str] = None, domain: Optional[str] = None, origin: Optional[str] = None
    ) -> List[PlannedTask]:
        sql = "SELECT * FROM planned_tasks WHERE 1=1"
        params = []
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
                loc = json.loads(r["location_json"]) if ("location_json" in r.keys() and r["location_json"]) else None
                results.append(PlannedTask(
                    id=r["id"],
                    title=r["title"],
                    domain=r["domain"],
                    scheduled_time=r["scheduled_time"],
                    recurrence=r["recurrence"],
                    status=r["status"],
                    completed_at=r["completed_at"],
                    verified_action_id=r["verified_action_id"],
                    created_at=r["created_at"],
                    origin=r["origin"] if ("origin" in r.keys() and r["origin"]) else "manual",
                    raw_statement=r["raw_statement"] if "raw_statement" in r.keys() else None,
                    confidence=r["confidence"] if ("confidence" in r.keys() and r["confidence"] is not None) else 1.0,
                    relative_time_anchor=r["relative_time_anchor"] if "relative_time_anchor" in r.keys() else None,
                    session_id=r["session_id"] if "session_id" in r.keys() else None,
                    location=loc,
                ))
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
                    relative_time_anchor = ?, session_id = ?, location_json = ?
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
        if not pending_tasks:
            return None

        action_text = f"{action.action_type} {action.raw_statement}".lower()

        # Check each pending task for keyword overlap
        for task in pending_tasks:
            stop_words = {"the", "and", "for", "with", "this", "that", "from", "into", "over", "take", "make", "turn", "out"}
            words = [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", task.title.lower()) if w not in stop_words]
            if words and any(w in action_text for w in words):
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
        for com in open_commitments:
            stop_words = {"the", "and", "for", "with", "this", "that", "from", "into", "over", "take", "make", "turn", "out"}
            com_words = [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", com.description.lower()) if w not in stop_words]
            contact_words = [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", com.contact_name.lower()) if w not in stop_words]
            if com_words and any(w in action_text for w in com_words) and (not contact_words or any(cw in action_text for cw in contact_words)):
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
                (id, action_type, domain, raw_statement, confidence, timestamp, is_revoked, matched_task_id, location_json, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ))
            if self._has_fts:
                cursor.execute("""
                    INSERT INTO fts_actions(rowid, action_type, raw_statement)
                    SELECT rowid, action_type, raw_statement FROM verified_actions WHERE id = ?
                """, (rec_id,))
            conn.commit()
        return rec_id


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
                loc = json.loads(row["location_json"]) if ("location_json" in row.keys() and row["location_json"]) else None
                return VerifiedAction(
                    id=row["id"],
                    action_type=row["action_type"],
                    domain=row["domain"],
                    raw_statement=row["raw_statement"],
                    confidence=row["confidence"],
                    timestamp=row["timestamp"],
                    is_revoked=bool(row["is_revoked"]),
                    matched_task_id=row["matched_task_id"] if "matched_task_id" in row.keys() else None,
                    session_id=row["session_id"] if "session_id" in row.keys() else None,
                    location=loc,
                )
        return None

    def list_recent_actions(
        self, limit: int = 10, domain: Optional[str] = None
    ) -> List[VerifiedAction]:
        sql = "SELECT * FROM verified_actions WHERE is_revoked = 0"
        params = []
        if domain and domain != "all":
            sql += " AND domain = ?"
            params.append(domain)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        results = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql, params).fetchall()
            for row in rows:
                loc = json.loads(row["location_json"]) if ("location_json" in row.keys() and row["location_json"]) else None
                results.append(
                    VerifiedAction(
                        id=row["id"],
                        action_type=row["action_type"],
                        domain=row["domain"],
                        raw_statement=row["raw_statement"],
                        confidence=row["confidence"],
                        timestamp=row["timestamp"],
                        is_revoked=bool(row["is_revoked"]),
                        matched_task_id=row["matched_task_id"] if "matched_task_id" in row.keys() else None,
                        session_id=row["session_id"] if "session_id" in row.keys() else None,
                        location=loc,
                    )
                )
        return results

    # =========================================================================
    # Social Recall
    # =========================================================================
    def save_social_contact(self, contact: SocialEntity) -> str:
        rec_id = contact.id or str(uuid.uuid4())
        contact.id = rec_id

        # Normalize commitments and persist structured bilateral commitments
        structured_commitments = contact.get_commitments_as_objects()
        for com in structured_commitments:
            if not com.contact_name:
                com.contact_name = contact.person_name
            self.save_social_commitment(com)

        # Retain json representation in contact record for fast retrieval/backward compatibility
        commitments_payload = [
            c.model_dump() if hasattr(c, "model_dump") else c
            for c in structured_commitments
        ]
        commitments_str = json.dumps(commitments_payload, ensure_ascii=False)
        topics_str = json.dumps(contact.key_topics, ensure_ascii=False)

        # Preserve existing web_profile_json if not provided in incoming contact
        web_profile_str = None
        if contact.web_profile:
            web_profile_str = contact.web_profile.model_dump_json()
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                existing_row = cursor.execute(
                    "SELECT web_profile_json FROM social_contacts WHERE id = ? OR LOWER(person_name) = LOWER(?)",
                    (rec_id, contact.person_name),
                ).fetchone()
                if existing_row and "web_profile_json" in existing_row.keys() and existing_row["web_profile_json"]:
                    web_profile_str = existing_row["web_profile_json"]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO social_contacts
                (id, person_name, company_or_role, contact_info, commitments_json, key_topics_json, timestamp, web_profile_json, location_encountered, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            person_name = row["person_name"]
            commitments = self.list_social_commitments(contact_name=person_name)
            if not commitments and row["commitments_json"]:
                try:
                    commitments = json.loads(row["commitments_json"])
                except Exception:
                    commitments = []
            topics = json.loads(row["key_topics_json"]) if row["key_topics_json"] else []
            web_profile = None
            if "web_profile_json" in row.keys() and row["web_profile_json"]:
                try:
                    web_profile = SocialWebProfile.model_validate_json(row["web_profile_json"])
                except Exception:
                    pass
            loc_enc = row["location_encountered"] if ("location_encountered" in row.keys() and row["location_encountered"]) else None
            session_id = row["session_id"] if ("session_id" in row.keys() and row["session_id"]) else None
            return SocialEntity(
                id=row["id"],
                person_name=row["person_name"],
                company_or_role=row["company_or_role"],
                contact_info=row["contact_info"],
                commitments=commitments,
                key_topics=topics,
                web_profile=web_profile,
                location_encountered=loc_enc,
                session_id=session_id,
                timestamp=row["timestamp"],
            )

    def update_contact_web_profile(
        self, contact_id_or_name: str, profile: SocialWebProfile
    ) -> bool:
        target = contact_id_or_name.strip()
        profile_json = profile.model_dump_json()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE social_contacts
                SET web_profile_json = ?
                WHERE id = ? OR LOWER(person_name) = LOWER(?)
                """,
                (profile_json, target, target),
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
                person_name = row["person_name"]
                commitments = self.list_social_commitments(contact_name=person_name)
                if not commitments and row["commitments_json"]:
                    try:
                        raw_c = json.loads(row["commitments_json"])
                        commitments = raw_c
                    except Exception:
                        commitments = []
                topics = json.loads(row["key_topics_json"]) if row["key_topics_json"] else []
                web_profile = None
                if "web_profile_json" in row.keys() and row["web_profile_json"]:
                    try:
                        web_profile = SocialWebProfile.model_validate_json(row["web_profile_json"])
                    except Exception:
                        pass
                loc_enc = row["location_encountered"] if ("location_encountered" in row.keys() and row["location_encountered"]) else None
                session_id = row["session_id"] if ("session_id" in row.keys() and row["session_id"]) else None
                results.append(
                    SocialEntity(
                        id=row["id"],
                        person_name=row["person_name"],
                        company_or_role=row["company_or_role"],
                        contact_info=row["contact_info"],
                        commitments=commitments,
                        key_topics=topics,
                        web_profile=web_profile,
                        location_encountered=loc_enc,
                        session_id=session_id,
                        timestamp=row["timestamp"],
                    )
                )
        return results

    def save_social_commitment(self, commitment: SocialCommitment) -> str:
        rec_id = commitment.id or str(uuid.uuid4())
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
                return SocialCommitment(
                    id=row["id"],
                    contact_name=row["contact_name"],
                    debtor=row["debtor"],
                    description=row["description"],
                    due_date_raw=row["due_date_raw"],
                    normalized_deadline=row["normalized_deadline"],
                    status=row["status"],
                    auto_scheduled_task_id=row["auto_scheduled_task_id"],
                    created_at=row["created_at"],
                )
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
                results.append(
                    SocialCommitment(
                        id=r["id"],
                        contact_name=r["contact_name"],
                        debtor=r["debtor"],
                        description=r["description"],
                        due_date_raw=r["due_date_raw"],
                        normalized_deadline=r["normalized_deadline"],
                        status=r["status"],
                        auto_scheduled_task_id=r["auto_scheduled_task_id"],
                        created_at=r["created_at"],
                    )
                )
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
                (id, topic_title, context_type, executive_summary_json, explanatory_synthesis, deep_dive_markdown, web_sources_json, action_items_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec_id,
                briefing.topic_title,
                briefing.context_type,
                exec_summary_str,
                briefing.explanatory_synthesis or "",
                briefing.deep_dive_markdown,
                sources_str,
                items_str,
                briefing.created_at
            ))
            if self._has_fts:
                cursor.execute("""
                    INSERT INTO fts_briefings(rowid, topic_title, deep_dive_markdown)
                    SELECT rowid, topic_title, deep_dive_markdown FROM topic_briefings WHERE id = ?
                """, (rec_id,))
            conn.commit()
        return rec_id

    def get_topic_briefing(self, query: Optional[str] = None) -> Optional[BriefingReport]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if query and query.strip():
                clean_target = query.strip()
                clean_query = f"%{clean_target.lower()}%"
                sql = """
                    SELECT * FROM topic_briefings
                    WHERE id = ? OR LOWER(topic_title) LIKE ? OR LOWER(deep_dive_markdown) LIKE ? OR LOWER(COALESCE(explanatory_synthesis, '')) LIKE ?
                    ORDER BY created_at DESC LIMIT 1
                """
                row = cursor.execute(sql, (clean_target, clean_query, clean_query, clean_query)).fetchone()
            else:
                sql = "SELECT * FROM topic_briefings ORDER BY created_at DESC LIMIT 1"
                row = cursor.execute(sql).fetchone()

            if row:
                exec_summary = json.loads(row["executive_summary_json"]) if row["executive_summary_json"] else []
                sources = json.loads(row["web_sources_json"]) if row["web_sources_json"] else []
                items = json.loads(row["action_items_json"]) if row["action_items_json"] else []
                synthesis = row["explanatory_synthesis"] if "explanatory_synthesis" in row.keys() and row["explanatory_synthesis"] else ""
                return BriefingReport(
                    id=row["id"],
                    topic_title=row["topic_title"],
                    context_type=row["context_type"],
                    executive_summary=exec_summary,
                    explanatory_synthesis=synthesis,
                    deep_dive_markdown=row["deep_dive_markdown"] or "",
                    web_sources=sources,
                    action_items=items,
                    created_at=row["created_at"],
                )
        return None

    def list_topic_briefings(self, limit: int = 10) -> List[BriefingReport]:
        results = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(
                "SELECT * FROM topic_briefings ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            for row in rows:
                exec_summary = json.loads(row["executive_summary_json"]) if row["executive_summary_json"] else []
                sources = json.loads(row["web_sources_json"]) if row["web_sources_json"] else []
                items = json.loads(row["action_items_json"]) if row["action_items_json"] else []
                synthesis = row["explanatory_synthesis"] if "explanatory_synthesis" in row.keys() and row["explanatory_synthesis"] else ""
                results.append(
                    BriefingReport(
                        id=row["id"],
                        topic_title=row["topic_title"],
                        context_type=row["context_type"],
                        executive_summary=exec_summary,
                        explanatory_synthesis=synthesis,
                        deep_dive_markdown=row["deep_dive_markdown"] or "",
                        web_sources=sources,
                        action_items=items,
                        created_at=row["created_at"],
                    )
                )
        return results

    def patch_utterance_speaker(
        self, chunk_id: str, speaker_id: str, speaker_role: Optional[str] = None
    ) -> bool:
        """Retrospectively patches speaker metadata on stored actions/tasks and records diarization."""
        patched = False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO utterance_diarization (chunk_id, speaker_id, speaker_role, updated_at) VALUES (?, ?, ?, ?)",
                (chunk_id, speaker_id, speaker_role or "unknown", datetime.now(timezone.utc).isoformat())
            )
            cursor.execute(
                "UPDATE planned_tasks SET session_id = ? WHERE id = ? OR session_id = ?",
                (speaker_id, chunk_id, chunk_id),
            )
            if cursor.rowcount > 0:
                patched = True
            cursor.execute(
                "UPDATE verified_actions SET matched_task_id = ? WHERE id = ?",
                (speaker_id, chunk_id),
            )
            if cursor.rowcount > 0:
                patched = True
            conn.commit()
        return True

    # =========================================================================
    # Macro Session & Micro-Event Decoupling (Milestone 3.2)
    # =========================================================================
    def save_session_dossier(self, dossier: SessionDossier) -> str:
        loc_str = json.dumps(dossier.location, ensure_ascii=False) if dossier.location else None
        chunks_str = json.dumps(dossier.transcript_chunks, ensure_ascii=False)
        points_str = json.dumps(dossier.key_discussion_points, ensure_ascii=False)
        events_payload = [
            e.model_dump() if hasattr(e, "model_dump") else e
            for e in dossier.linked_micro_events
        ]
        events_str = json.dumps(events_payload, ensure_ascii=False)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO session_dossiers
                (session_id, title, domain, start_time, last_updated_at, concluded_at,
                 status, location_json, transcript_chunks_json, key_discussion_points_json,
                 linked_micro_events_json, final_briefing_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dossier.session_id,
                dossier.title,
                dossier.domain,
                dossier.start_time,
                dossier.last_updated_at,
                dossier.concluded_at,
                dossier.status,
                loc_str,
                chunks_str,
                points_str,
                events_str,
                dossier.final_briefing_id,
                dossier.start_time,
            ))
            conn.commit()
        return dossier.session_id

    def get_session_dossier(self, session_id: Optional[str] = None) -> Optional[SessionDossier]:
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

            loc = json.loads(row["location_json"]) if row["location_json"] else None
            chunks = json.loads(row["transcript_chunks_json"]) if row["transcript_chunks_json"] else []
            points = json.loads(row["key_discussion_points_json"]) if row["key_discussion_points_json"] else []
            
            raw_events = json.loads(row["linked_micro_events_json"]) if row["linked_micro_events_json"] else []
            linked_events: List[MicroEventRef] = []
            for item in raw_events:
                try:
                    linked_events.append(MicroEventRef(**item) if isinstance(item, dict) else item)
                except Exception:
                    pass

            briefing_report = None
            if row["final_briefing_id"]:
                briefing_report = self.get_topic_briefing(row["final_briefing_id"])

            return SessionDossier(
                session_id=row["session_id"],
                title=row["title"],
                domain=row["domain"],
                start_time=row["start_time"],
                last_updated_at=row["last_updated_at"],
                concluded_at=row["concluded_at"],
                status=row["status"],
                location=loc,
                transcript_chunks=chunks,
                key_discussion_points=points,
                linked_micro_events=linked_events,
                final_briefing_id=row["final_briefing_id"],
                briefing_report=briefing_report,
            )

    def list_session_dossiers(
        self, status: Optional[str] = None, limit: int = 10
    ) -> List[SessionDossier]:
        sql = "SELECT * FROM session_dossiers "
        params = []
        if status:
            sql += "WHERE status = ? "
            params.append(status)
        sql += "ORDER BY start_time DESC LIMIT ?"
        params.append(limit)

        results = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql, params).fetchall()
            for row in rows:
                loc = json.loads(row["location_json"]) if row["location_json"] else None
                chunks = json.loads(row["transcript_chunks_json"]) if row["transcript_chunks_json"] else []
                points = json.loads(row["key_discussion_points_json"]) if row["key_discussion_points_json"] else []
                raw_events = json.loads(row["linked_micro_events_json"]) if row["linked_micro_events_json"] else []
                linked_events: List[MicroEventRef] = []
                for item in raw_events:
                    try:
                        linked_events.append(MicroEventRef(**item) if isinstance(item, dict) else item)
                    except Exception:
                        pass

                briefing_report = None
                if row["final_briefing_id"]:
                    briefing_report = self.get_topic_briefing(row["final_briefing_id"])

                results.append(
                    SessionDossier(
                        session_id=row["session_id"],
                        title=row["title"],
                        domain=row["domain"],
                        start_time=row["start_time"],
                        last_updated_at=row["last_updated_at"],
                        concluded_at=row["concluded_at"],
                        status=row["status"],
                        location=loc,
                        transcript_chunks=chunks,
                        key_discussion_points=points,
                        linked_micro_events=linked_events,
                        final_briefing_id=row["final_briefing_id"],
                        briefing_report=briefing_report,
                    )
                )
        return results

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
            dossier.last_updated_at = now_iso

        self.save_session_dossier(dossier)
        return True

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

    def close(self) -> None:
        """Close connection pools or resources if applicable."""
        pass


from datetime import datetime
import json
import re
import sqlite3
import uuid
from typing import List, Optional

from src.core.schemas import BriefingReport, SocialEntity, VerifiedAction, PlannedTask
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
                    matched_task_id TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_type ON verified_actions (action_type);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_time ON verified_actions (timestamp DESC);")

            # 2. Social Contacts Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS social_contacts (
                    id TEXT PRIMARY KEY,
                    person_name TEXT NOT NULL,
                    company_or_role TEXT,
                    contact_info TEXT,
                    commitments_json TEXT,
                    key_topics_json TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_social_name ON social_contacts (person_name);")

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

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO planned_tasks
                (id, title, domain, scheduled_time, recurrence, status, completed_at, verified_action_id, created_at,
                 origin, raw_statement, confidence, relative_time_anchor, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ))
            conn.commit()
        return rec_id

    def get_planned_task(self, task_id: str) -> Optional[PlannedTask]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute("SELECT * FROM planned_tasks WHERE id = ?", (task_id,)).fetchone()
            if row:
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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE planned_tasks
                SET title = ?, domain = ?, scheduled_time = ?, recurrence = ?,
                    status = ?, completed_at = ?, verified_action_id = ?,
                    origin = ?, raw_statement = ?, confidence = ?,
                    relative_time_anchor = ?, session_id = ?
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
                return task

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

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO verified_actions 
                (id, action_type, domain, raw_statement, confidence, timestamp, is_revoked, matched_task_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec_id,
                action.action_type.lower(),
                action.domain,
                action.raw_statement,
                action.confidence,
                action.timestamp,
                1 if action.is_revoked else 0,
                action.matched_task_id
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
            WHERE (action_type LIKE ? OR raw_statement LIKE ?)
              AND is_revoked = 0
        """
        params = [clean_query, clean_query]

        if target_date:
            sql += " AND timestamp LIKE ?"
            params.append(f"{target_date}%")

        sql += " ORDER BY timestamp DESC LIMIT 1"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute(sql, params).fetchone()
            if row:
                return VerifiedAction(
                    id=row["id"],
                    action_type=row["action_type"],
                    domain=row["domain"],
                    raw_statement=row["raw_statement"],
                    confidence=row["confidence"],
                    timestamp=row["timestamp"],
                    is_revoked=bool(row["is_revoked"]),
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
                results.append(
                    VerifiedAction(
                        id=row["id"],
                        action_type=row["action_type"],
                        domain=row["domain"],
                        raw_statement=row["raw_statement"],
                        confidence=row["confidence"],
                        timestamp=row["timestamp"],
                        is_revoked=bool(row["is_revoked"]),
                    )
                )
        return results

    # =========================================================================
    # Social Recall
    # =========================================================================
    def save_social_contact(self, contact: SocialEntity) -> str:
        rec_id = contact.id or str(uuid.uuid4())
        contact.id = rec_id

        commitments_str = json.dumps(contact.commitments, ensure_ascii=False)
        topics_str = json.dumps(contact.key_topics, ensure_ascii=False)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO social_contacts
                (id, person_name, company_or_role, contact_info, commitments_json, key_topics_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                rec_id,
                contact.person_name,
                contact.company_or_role,
                contact.contact_info,
                commitments_str,
                topics_str,
                contact.timestamp
            ))
            if self._has_fts:
                cursor.execute("""
                    INSERT INTO fts_social(rowid, person_name, company_or_role)
                    SELECT rowid, person_name, company_or_role FROM social_contacts WHERE id = ?
                """, (rec_id,))
            conn.commit()
        return rec_id

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
                commitments = json.loads(row["commitments_json"]) if row["commitments_json"] else []
                topics = json.loads(row["key_topics_json"]) if row["key_topics_json"] else []
                results.append(
                    SocialEntity(
                        id=row["id"],
                        person_name=row["person_name"],
                        company_or_role=row["company_or_role"],
                        contact_info=row["contact_info"],
                        commitments=commitments,
                        key_topics=topics,
                        timestamp=row["timestamp"],
                    )
                )
        return results

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
                clean_query = f"%{query.strip().lower()}%"
                sql = """
                    SELECT * FROM topic_briefings
                    WHERE LOWER(topic_title) LIKE ? OR LOWER(deep_dive_markdown) LIKE ? OR LOWER(COALESCE(explanatory_synthesis, '')) LIKE ?
                    ORDER BY created_at DESC LIMIT 1
                """
                row = cursor.execute(sql, (clean_query, clean_query, clean_query)).fetchone()
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

    def close(self) -> None:
        """Close connection pools or resources if applicable."""
        pass

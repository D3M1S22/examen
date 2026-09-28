"""SQLite implementation of AbstractContextStore with Full-Text Search (FTS5)."""

import json
import sqlite3
import uuid
from typing import List, Optional

from src.core.schemas import BriefingReport, SocialEntity, VerifiedAction
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

            # 1. Tabella Azioni Verificate
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS verified_actions (
                    id TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    raw_statement TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    is_revoked INTEGER DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_type ON verified_actions (action_type);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_time ON verified_actions (timestamp DESC);")

            # 2. Tabella Contatti Social
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

            # 3. Tabella Topic Briefings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS topic_briefings (
                    id TEXT PRIMARY KEY,
                    topic_title TEXT NOT NULL,
                    context_type TEXT NOT NULL,
                    executive_summary_json TEXT,
                    deep_dive_markdown TEXT,
                    web_sources_json TEXT,
                    action_items_json TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_briefings_time ON topic_briefings (created_at DESC);")

            # 4. Configurazione FTS5 (se supportato dall'ambiente SQLite)
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
                # Fallback trasparente a LIKE se FTS5 non è abilitato
                self._has_fts = False

            conn.commit()

    # =========================================================================
    # Action State
    # =========================================================================
    def save_action(self, action: VerifiedAction) -> str:
        rec_id = action.id or str(uuid.uuid4())
        action.id = rec_id

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO verified_actions 
                (id, action_type, domain, raw_statement, confidence, timestamp, is_revoked)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                rec_id,
                action.action_type.lower(),
                action.domain,
                action.raw_statement,
                action.confidence,
                action.timestamp,
                1 if action.is_revoked else 0
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
                (id, topic_title, context_type, executive_summary_json, deep_dive_markdown, web_sources_json, action_items_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec_id,
                briefing.topic_title,
                briefing.context_type,
                exec_summary_str,
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
                    WHERE LOWER(topic_title) LIKE ? OR LOWER(deep_dive_markdown) LIKE ?
                    ORDER BY created_at DESC LIMIT 1
                """
                row = cursor.execute(sql, (clean_query, clean_query)).fetchone()
            else:
                sql = "SELECT * FROM topic_briefings ORDER BY created_at DESC LIMIT 1"
                row = cursor.execute(sql).fetchone()

            if row:
                exec_summary = json.loads(row["executive_summary_json"]) if row["executive_summary_json"] else []
                sources = json.loads(row["web_sources_json"]) if row["web_sources_json"] else []
                items = json.loads(row["action_items_json"]) if row["action_items_json"] else []
                return BriefingReport(
                    id=row["id"],
                    topic_title=row["topic_title"],
                    context_type=row["context_type"],
                    executive_summary=exec_summary,
                    deep_dive_markdown=row["deep_dive_markdown"] or "",
                    web_sources=sources,
                    action_items=items,
                    created_at=row["created_at"],
                )
        return None

    def close(self) -> None:
        """Chiude eventuali pool o risorse se necessario."""
        pass

"""Shared storage rules (src/core/storage/rules.py)."""

import sqlite3

import pytest

from src.core.schemas import PlannedTask, SocialCommitment, VerifiedAction
from src.core.storage import rules

LIKE_CASES = [
    ("Ferro da stiro", "%ferro%"),
    ("FERRO", "%ferro%"),
    ("ferro", "%FERRO%"),
    ("Città", "%CITTÀ%"),        # SQLite folds ASCII only: no match
    ("città", "%città%"),
    ("gas_off", "%gas_off%"),
    ("gasXoff", "%gas_off%"),     # `_` matches one character
    ("gas off", "%gas%off%"),
    ("", "%%"),
    ("abc", "abc"),
    ("abcd", "abc"),
    ("a\nb", "%a_b%"),
    ("100%", "%100%%"),
    (None, "%x%"),
]


@pytest.mark.parametrize("value,pattern", LIKE_CASES)
def test_sql_like_matches_sqlite(value, pattern):
    conn = sqlite3.connect(":memory:")
    expected = conn.execute("SELECT ? LIKE ?", (value, pattern)).fetchone()[0]
    assert rules.sql_like(value, pattern) == bool(expected)


def test_keyword_matching_rules():
    task = PlannedTask(title="Take out the trash", domain="routine")
    action = VerifiedAction(action_type="trash_out", domain="routine", raw_statement="Ho portato fuori il trash",
                            confidence=0.9)
    assert rules.keywords(task.title) == ["trash"]
    assert rules.action_matches_task(rules.action_text(action), task)
    assert not rules.action_matches_task("nothing here", task)
    com = SocialCommitment(contact_name="Marco Rossi", debtor="user", description="send the slides")
    assert rules.action_matches_commitment("i will send slides to marco", com)
    assert not rules.action_matches_commitment("i will send slides to luca", com)


def test_commitment_key_is_case_insensitive_but_debtor_sensitive():
    a = rules.commitment_key("Marco", "Send Slides", "user")
    assert a == rules.commitment_key("marco", "send slides", "user")
    assert a != rules.commitment_key("marco", "send slides", "contact")


def test_latency_summary():
    assert rules.latency_summary([])["sample_count"] == 0
    summary = rules.latency_summary([30.0, 10.0, 20.0])
    assert summary == {"sample_count": 3, "average_ms": 20.0, "latest_ms": 30.0, "min_ms": 10.0, "max_ms": 30.0}

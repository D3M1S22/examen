"""Storage errors shared by the SQLite and DynamoDB backends."""


class UniqueConflict(Exception):
    """A uniqueness rule was violated (for example a Bee account already linked to another user)."""

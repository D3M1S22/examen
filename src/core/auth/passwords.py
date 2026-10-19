"""Password hashing with scrypt (hashlib, no extra dependency).

scrypt is memory-hard and recommended by OWASP for password storage. Parameters follow OWASP's
minimum (N=2^17, r=8, p=1, ~128 MiB) unless overridden for tests. Hash format::

    scrypt$<log2 N>$<r>$<p>$<salt b64>$<hash b64>

Plain-text passwords are never stored, logged or returned.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Optional

_LOG2_N = 17
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _derive(password: str, salt: bytes, log2_n: int, r: int, p: int) -> bytes:
    n = 1 << log2_n
    maxmem = 128 * r * (n + p + 2) + 1024 * 1024
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=maxmem, dklen=_DKLEN)


def hash_password(password: str, log2_n: Optional[int] = None) -> str:
    salt = os.urandom(_SALT_BYTES)
    cost = _LOG2_N if log2_n is None else log2_n
    digest = _derive(password, salt, cost, _R, _P)
    return f"scrypt${cost}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, log2_n, r, p, salt_b64, hash_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(hash_b64)
        actual = _derive(password, base64.b64decode(salt_b64), int(log2_n), int(r), int(p))
    except Exception:
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(encoded: str) -> bool:
    try:
        scheme, log2_n, r, p, _, _ = encoded.split("$")
    except ValueError:
        return True
    return scheme != "scrypt" or int(log2_n) < _LOG2_N or int(r) != _R or int(p) != _P


# A hash of a random password: verified when the email is unknown, so a login attempt takes the
# same time whether or not the account exists (no account enumeration through timing).
_DUMMY_HASH: Optional[str] = None


def dummy_verify(password: str) -> None:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(os.urandom(16).hex())
    verify_password(password, _DUMMY_HASH)


def password_problem(password: str, email: str, min_length: int) -> Optional[str]:
    """Returns why a new password is rejected, or None when it is acceptable (NIST 800-63B style:
    length over composition rules)."""
    if not isinstance(password, str) or len(password) < min_length:
        return f"Password must be at least {min_length} characters."
    if len(password) > 256:
        return "Password must be at most 256 characters."
    lowered = password.lower()
    local = (email or "").split("@")[0].lower()
    if local and len(local) >= 4 and local in lowered:
        return "Password must not contain your email address."
    if len(set(password)) < 4:
        return "Password is too repetitive."
    if lowered in _COMMON:
        return "This password is too common."
    return None


_COMMON = {
    "password", "password1", "password123", "1234567890", "12345678901", "qwertyuiop", "iloveyou12",
    "letmein123", "welcome123", "administrator", "passw0rd123", "qwerty12345", "1q2w3e4r5t", "abc1234567",
}

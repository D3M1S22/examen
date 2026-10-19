"""In-memory brute-force protection for login and registration.

Failures are counted per email (limit ``AUTH_MAX_LOGIN_FAILURES``) and per client address (5x that)
within ``AUTH_LOCKOUT_MINUTES``; beyond the limit attempts are refused until the window passes. Single-process only;
the AWS deployment should move this to a shared store.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Iterable

from src.core.config import settings


class FailureLimiter:
    def __init__(self) -> None:
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _window(self) -> float:
        return settings.auth_lockout_minutes * 60.0

    def _prune(self, key: str, now: float) -> Deque[float]:
        q = self._events[key]
        cutoff = now - self._window()
        while q and q[0] < cutoff:
            q.popleft()
        return q

    @staticmethod
    def _limit(key: str) -> int:
        # A client address is shared by everyone behind the same NAT: allow it more failures than
        # a single account, while still stopping a password-spraying client.
        base = settings.auth_max_login_failures
        return base * 5 if key.startswith("ip:") else base

    def blocked(self, keys: Iterable[str]) -> float:
        """Seconds until the caller may retry (0 when allowed)."""
        now = time.monotonic()
        wait = 0.0
        with self._lock:
            for key in keys:
                q = self._prune(key, now)
                if len(q) >= self._limit(key):
                    wait = max(wait, q[0] + self._window() - now)
        return wait

    def fail(self, keys: Iterable[str]) -> None:
        now = time.monotonic()
        with self._lock:
            for key in keys:
                self._prune(key, now).append(now)

    def clear(self, keys: Iterable[str]) -> None:
        with self._lock:
            for key in keys:
                self._events.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


login_limiter = FailureLimiter()

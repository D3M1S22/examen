"""In-memory sliding-window counters for the health monitor (docs/next_steps/admin_console/03 §5).

Counts (calls, fallbacks, events by code) and samples (latencies, LLM slot occupancy) kept for one
hour, optionally per user. Process-local: a restart starts empty, so rate rules wait for their
minimum sample. Thread-safe (pipeline nodes run in worker threads).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, List, Optional, Tuple

MAX_WINDOW_SECONDS = 3600.0


class Metrics:
    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
        self._series: Dict[Tuple[str, Optional[str]], Deque[Tuple[float, float]]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, q: Deque[Tuple[float, float]], now: float) -> None:
        cutoff = now - MAX_WINDOW_SECONDS
        while q and q[0][0] < cutoff:
            q.popleft()

    def incr(self, name: str, user_id: Optional[str] = None, value: float = 1.0) -> None:
        now = self.clock()
        with self._lock:
            for key in {(name, None), (name, user_id)}:
                q = self._series[key]
                q.append((now, value))
                self._prune(q, now)

    observe = incr  # samples (latency, occupancy) share the storage; read them with ``values``

    def values(self, name: str, window: float, user_id: Optional[str] = None) -> List[float]:
        now = self.clock()
        with self._lock:
            q = self._series.get((name, user_id))
            if not q:
                return []
            self._prune(q, now)
            return [v for t, v in q if t >= now - window]

    def count(self, name: str, window: float, user_id: Optional[str] = None) -> float:
        return float(sum(self.values(name, window, user_id)))

    def users(self, name: str) -> List[str]:
        with self._lock:
            return sorted({uid for (n, uid) in self._series if n == name and uid is not None})

    def reset(self) -> None:
        with self._lock:
            self._series.clear()


def percentile(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


metrics = Metrics()

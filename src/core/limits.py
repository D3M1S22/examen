"""Process-wide limits shared by every user's runtime (docs/13_multi_user_accounts.md §5).

``llm_slot()`` bounds concurrent LLM work (gatekeeper screening and pipeline dispatches, live and
backfill) across all users to ``MAX_CONCURRENT_LLM_CALLS``, so one user's history backfill cannot
exhaust the Bedrock quota or starve the live stream of everyone else.

The limit is read on every acquire, so an admin override applies without a restart
(docs/next_steps/admin_console/02 §4.5). ``llm_slots_in_use()`` feeds the health monitor.
"""

import asyncio
import weakref
from contextlib import asynccontextmanager
from typing import AsyncIterator

from src.core.config import settings


class _ResizableLimiter:
    """A semaphore whose capacity follows ``settings.max_concurrent_llm_calls``."""

    def __init__(self) -> None:
        self.in_use = 0
        self._condition = asyncio.Condition()

    @staticmethod
    def capacity() -> int:
        return max(1, int(settings.max_concurrent_llm_calls))

    async def acquire(self) -> None:
        async with self._condition:
            await self._condition.wait_for(lambda: self.in_use < self.capacity())
            self.in_use += 1

    async def release(self) -> None:
        async with self._condition:
            self.in_use -= 1
            self._condition.notify_all()

    async def resized(self) -> None:
        async with self._condition:
            self._condition.notify_all()


# One limiter per event loop (tests run several loops in one process)
_limiters: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _ResizableLimiter]" = weakref.WeakKeyDictionary()


def _limiter() -> _ResizableLimiter:
    loop = asyncio.get_running_loop()
    limiter = _limiters.get(loop)
    if limiter is None:
        limiter = _ResizableLimiter()
        _limiters[loop] = limiter
    return limiter


@asynccontextmanager
async def llm_slot() -> AsyncIterator[None]:
    limiter = _limiter()
    await limiter.acquire()
    try:
        yield
    finally:
        await limiter.release()


def llm_slots_in_use() -> int:
    return sum(limiter.in_use for limiter in list(_limiters.values()))


async def notify_llm_limit_changed() -> None:
    """Wakes waiters after the limit was raised at runtime."""
    limiter = _limiters.get(asyncio.get_running_loop())
    if limiter is not None:
        await limiter.resized()

"""Process-wide limits shared by every user's runtime (docs/13_multi_user_accounts.md §5).

``llm_slot()`` bounds concurrent LLM work (gatekeeper screening and pipeline dispatches, live and
backfill) across all users to ``MAX_CONCURRENT_LLM_CALLS``, so one user's history backfill cannot
exhaust the Bedrock quota or starve the live stream of everyone else.
"""

import asyncio
import weakref
from contextlib import asynccontextmanager
from typing import AsyncIterator

from src.core.config import settings

# One semaphore per event loop (tests run several loops in one process)
_semaphores: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


def _semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _semaphores.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(max(1, settings.max_concurrent_llm_calls))
        _semaphores[loop] = sem
    return sem


@asynccontextmanager
async def llm_slot() -> AsyncIterator[None]:
    async with _semaphore():
        yield

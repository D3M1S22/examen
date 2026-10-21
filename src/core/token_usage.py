"""Token usage per model (docs/next_steps/admin_console/03 §8).

Every model is built by ``src/core/models.py``, which attaches a ``TokenUsageHandler`` to chat models
and returns ``CountingBedrockEmbeddings`` for embeddings. Both feed ``record()``: totals accumulate in
memory per (hour, provider, model, role, user) and ``flush()`` upserts them into ``ops.db`` in one
transaction (health monitor tick, shutdown, before every read). Counting must never break a model
call: every failure here is swallowed.

Only counts are stored (no prompt, no answer): the admin sees how many tokens each model and user
consumed, never what was said.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from langchain_core.callbacks import BaseCallbackHandler

from src.core.tenancy import get_tenant_id

logger = logging.getLogger("examen.ops.tokens")  # examen.ops: never echoed into the service log

Key = Tuple[str, str, str, str, str]  # hour, provider, model_id, role, user_id
_FIELDS = ("calls", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")

_pending: Dict[Key, Dict[str, int]] = {}
_lock = threading.Lock()


def _hour(now: Optional[datetime] = None) -> str:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def record(provider: str, model_id: str, role: str, *, input_tokens: int = 0, output_tokens: int = 0,
           cache_read_tokens: int = 0, cache_write_tokens: int = 0, user_id: Any = None,
           calls: int = 1, now: Optional[datetime] = None) -> None:
    """Adds one model call to the in-memory totals (thread-safe, no I/O)."""
    try:
        uid = get_tenant_id() if user_id is None else user_id
        key = (_hour(now), provider or "unknown", model_id or "unknown", role or "other", uid or "")
        with _lock:
            row = _pending.setdefault(key, dict.fromkeys(_FIELDS, 0))
            row["calls"] += int(calls)
            row["input_tokens"] += max(0, int(input_tokens or 0))
            row["output_tokens"] += max(0, int(output_tokens or 0))
            row["cache_read_tokens"] += max(0, int(cache_read_tokens or 0))
            row["cache_write_tokens"] += max(0, int(cache_write_tokens or 0))
    except Exception as e:  # pragma: no cover - counting never breaks a model call
        logger.debug(f"token usage record failed: {e}")


def pending() -> List[Dict[str, Any]]:
    with _lock:
        return [dict(zip(("hour", "provider", "model_id", "role", "user_id"), k), **v) for k, v in _pending.items()]


def flush(store_getter: Optional[Callable] = None) -> int:
    """Upserts the accumulated totals into ops.db; returns how many rows were written."""
    with _lock:
        rows = [dict(zip(("hour", "provider", "model_id", "role", "user_id"), k), **v) for k, v in _pending.items()]
        _pending.clear()
    if not rows:
        return 0
    try:
        if store_getter is None:
            from src.core.ops_store import get_ops_store

            store_getter = get_ops_store
        store_getter().add_token_usage(rows)
        return len(rows)
    except Exception as e:
        logger.warning(f"token usage flush failed, {len(rows)} rows kept for the next flush: {e}")
        with _lock:  # put them back: nothing is lost on a transient database error
            for row in rows:
                key = (row["hour"], row["provider"], row["model_id"], row["role"], row["user_id"])
                target = _pending.setdefault(key, dict.fromkeys(_FIELDS, 0))
                for field in _FIELDS:
                    target[field] += row[field]
        return 0


def reset() -> None:
    """Test seam."""
    with _lock:
        _pending.clear()


def usage_from_message(message: Any) -> Dict[str, int]:
    """``AIMessage.usage_metadata`` → token counts (Bedrock Converse and OpenAI-compatible Mantle)."""
    usage = getattr(message, "usage_metadata", None) or {}
    details = usage.get("input_token_details") or {}
    cache_write = details.get("cache_creation") or 0
    if not cache_write:  # Bedrock splits cache writes by TTL
        cache_write = sum(v for k, v in details.items() if str(k).startswith("ephemeral_") and isinstance(v, int))
    return {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "cache_read_tokens": int(details.get("cache_read") or 0),
        "cache_write_tokens": int(cache_write or 0),
    }


class TokenUsageHandler(BaseCallbackHandler):
    """LangChain callback attached by the model factory: one ``record()`` per completed model call.

    It also fires when the caller wraps the model with ``.with_structured_output(...)``."""

    raise_error = False

    def __init__(self, provider: str, model_id: str, role: str):
        self.provider, self.model_id, self.role = provider, model_id, role

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        try:
            counted = False
            for generations in getattr(response, "generations", None) or []:
                for generation in generations:
                    message = getattr(generation, "message", None)
                    if message is None:
                        continue
                    record(self.provider, self.model_id, self.role, **usage_from_message(message))
                    counted = True
            if not counted:
                record(self.provider, self.model_id, self.role)  # no usage reported: count the call
        except Exception as e:  # pragma: no cover - counting never breaks a model call
            logger.debug(f"token usage callback failed: {e}")


def counting_embeddings_class():
    """``BedrockEmbeddings`` that records ``inputTextTokenCount`` (LangChain discards it)."""
    from langchain_aws import BedrockEmbeddings

    class CountingBedrockEmbeddings(BedrockEmbeddings):
        def _invoke_model(self, input_body: Dict[str, Any] = {}) -> Dict[str, Any]:  # noqa: B006 (upstream signature)
            response = super()._invoke_model(input_body)
            try:
                tokens = response.get("inputTextTokenCount") if isinstance(response, dict) else None
                record("bedrock", self.model_id, "embeddings", input_tokens=int(tokens or 0))
            except Exception as e:  # pragma: no cover
                logger.debug(f"embedding token count failed: {e}")
            return response

    return CountingBedrockEmbeddings

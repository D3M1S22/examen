"""Runs each MCP tool on behalf of the user who called it.

The streamable-HTTP session manager executes tool calls in its own tasks, not in the HTTP request's
context, so the tenant set by AuthMiddleware does not reach them. Each tool is therefore wrapped:
the wrapper receives FastMCP's ``Context``, reads the user id that AuthMiddleware stored on the HTTP
request (``request.state.examen_user_id``) and runs the tool inside ``tenant_scope``. The extra
``ctx`` parameter is hidden from the tool's JSON schema by FastMCP.
"""

from __future__ import annotations

import functools
import inspect
import typing
from typing import Any, Callable, Optional

from mcp.server.fastmcp import Context

from src.core.config import settings
from src.core.tenancy import is_valid_user_id, tenant_scope


def user_id_from_context(ctx: Optional[Context]) -> Optional[str]:
    if ctx is None:
        return None
    try:
        request = ctx.request_context.request
    except Exception:
        return None
    if request is None:
        return None
    state = (getattr(request, "scope", None) or {}).get("state") or {}
    uid = state.get("examen_user_id")
    return uid if is_valid_user_id(uid) else None


def tenant_tool(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wraps a sync or async MCP tool so it reads and writes only the calling user's data."""
    # Resolve string annotations (``from __future__ import annotations``) in the tool's own module:
    # FastMCP would otherwise evaluate them against this module's globals.
    hints = typing.get_type_hints(fn)
    raw = inspect.signature(fn)
    sig = raw.replace(
        parameters=[p.replace(annotation=hints.get(p.name, p.annotation)) for p in raw.parameters.values()],
        return_annotation=hints.get("return", raw.return_annotation),
    )
    ctx_param = inspect.Parameter("ctx", inspect.Parameter.KEYWORD_ONLY, annotation=Context, default=None)
    new_sig = sig.replace(parameters=[*sig.parameters.values(), ctx_param])

    def _resolve(ctx: Optional[Context]) -> Optional[str]:
        uid = user_id_from_context(ctx)
        if settings.auth_enabled and uid is None:
            raise PermissionError("Authentication required: send an EXAMEN access token as a Bearer token.")
        return uid

    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args: Any, ctx: Optional[Context] = None, **kwargs: Any) -> Any:
            with tenant_scope(_resolve(ctx)):
                return await fn(*args, **kwargs)

        async_wrapper.__signature__ = new_sig  # type: ignore[attr-defined]
        async_wrapper.__annotations__ = {**hints, "ctx": Context}
        return async_wrapper

    @functools.wraps(fn)
    def wrapper(*args: Any, ctx: Optional[Context] = None, **kwargs: Any) -> Any:
        with tenant_scope(_resolve(ctx)):
            return fn(*args, **kwargs)

    wrapper.__signature__ = new_sig  # type: ignore[attr-defined]
    wrapper.__annotations__ = {**hints, "ctx": Context}
    return wrapper

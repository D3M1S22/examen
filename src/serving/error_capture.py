"""Unhandled errors → service events (docs/next_steps/admin_console/03 §4.3).

``ErrorCaptureMiddleware`` wraps the ASGI app: a route that raises answers
``500 {"error": "internal_error", "event_id": …}`` and records ``serving.unhandled_exception``.
``install_asyncio_handler()`` reports exceptions of tasks nobody awaited (``system.task_exception``).
"""

from __future__ import annotations

import asyncio
import json
import logging

from src.core.service_log import report_event

logger = logging.getLogger("examen.ops.errors")  # traceback to journald only; the event is reported below


class ErrorCaptureMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def _send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception as e:
            ref = report_event("serving.unhandled_exception", "error",
                               f"{scope.get('method', '')} {scope.get('path', '')} failed: {type(e).__name__}: {e}",
                               component="serving", error=e, status_code=500)
            logger.error(f"Unhandled error {ref} on {scope.get('path', '')}", exc_info=True)
            if started:
                raise
            body = json.dumps({"error": "internal_error", "message": "Something went wrong on the server.",
                               "event_id": ref}).encode("utf-8")
            await send({"type": "http.response.start", "status": 500,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})


def install_asyncio_handler(loop: asyncio.AbstractEventLoop) -> None:
    previous = loop.get_exception_handler()

    def _handler(loop_, context):
        exc = context.get("exception")
        if exc is not None and not isinstance(exc, asyncio.CancelledError):
            report_event("system.task_exception", "error",
                         f"Background task failed: {type(exc).__name__}: {exc}", component="system", error=exc)
        if previous is not None:
            previous(loop_, context)
        else:
            loop_.default_exception_handler(context)

    loop.set_exception_handler(_handler)

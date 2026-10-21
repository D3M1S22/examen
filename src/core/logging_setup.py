"""Logging configuration for the server (docs/next_steps/admin_console/03 §4.1).

Before this, the ``examen.*`` loggers had no handler: Python's last-resort handler printed only
``WARNING``+ without timestamp or logger name, and every ``INFO`` was lost. ``setup_logging()`` adds:

- a stdout handler at ``LOG_LEVEL`` (journald on the homelab), with timestamp and logger name;
- the ``ServiceLogHandler`` (``WARNING``+ → sanitised admin service events);
- ``threading.excepthook`` → ``system.thread_exception``.

Idempotent: ``create_app()`` and ``main()`` both call it. ``set_log_level()`` applies a runtime override.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Optional

from src.core.config import settings

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_stdout_handler: Optional[logging.Handler] = None
_service_handler: Optional[logging.Handler] = None
_previous_thread_hook = None


def _level(name: Optional[str]) -> int:
    return getattr(logging, str(name or "INFO").upper(), logging.INFO)


def setup_logging(level: Optional[str] = None) -> logging.Logger:
    global _stdout_handler, _service_handler, _previous_thread_hook
    from src.core.service_log import ServiceLogHandler

    root = logging.getLogger("examen")
    if _stdout_handler is None:
        _stdout_handler = logging.StreamHandler(sys.stdout)
        _stdout_handler.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(_stdout_handler)
    if _service_handler is None:
        _service_handler = ServiceLogHandler()
        root.addHandler(_service_handler)
    root.propagate = False  # no duplicates if a library configures the root logger
    set_log_level(level or settings.log_level)

    if _previous_thread_hook is None:
        _previous_thread_hook = threading.excepthook

        def _thread_hook(args) -> None:
            from src.core.service_log import report_event

            if args.exc_type is not SystemExit:
                report_event("system.thread_exception", "error",
                             f"Thread {getattr(args.thread, 'name', '?')} crashed: {args.exc_type.__name__}",
                             component="system", user_id=None, error=args.exc_value)
            _previous_thread_hook(args)

        threading.excepthook = _thread_hook
    return root


def set_log_level(level: str) -> None:
    """stdout follows ``LOG_LEVEL``; the logger itself stays at least at WARNING for the service log."""
    value = _level(level)
    if _stdout_handler is not None:
        _stdout_handler.setLevel(value)
    logging.getLogger("examen").setLevel(min(value, logging.WARNING))

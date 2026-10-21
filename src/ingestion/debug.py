import logging
from typing import Any, Optional

# Debug sectors → logger names, so their output reaches journald and the service log
# (docs/next_steps/admin_console/03 §4.4)
_SECTOR_LOGGERS = {
    "BEE": "examen.ingestion.stream_convo",
    "ORCHESTRATOR": "examen.ingestion.orchestrator",
}


class Debug:
    def __init__(self, debug_mode: str, sector_name: str):
        self.debug_mode = debug_mode.lower()
        self.sector_name = sector_name.upper()
        self.logger = logging.getLogger(_SECTOR_LOGGERS.get(self.sector_name, f"examen.ingestion.{sector_name.lower()}"))

    def debug(self, message: str, log: bool = True):
        """Prints the message with the sector prefix if the debug mode matches; logs it at DEBUG.

        ``log=False`` for messages carrying what was said (transcripts never reach the logs)."""
        if self.debug_mode in ["all", "true", self.sector_name.lower()]:
            print(f"[{self.sector_name}] {message}")
        if log:
            self.logger.debug(message)

    def warn(self, message: str, code: Optional[str] = None, level: int = logging.WARNING,
             error: Optional[BaseException] = None, **ctx: Any) -> None:
        """A problem worth the admin's attention: logged (journald + service log) and printed in debug mode."""
        if self.debug_mode in ["all", "true", self.sector_name.lower()]:
            print(f"[{self.sector_name}] {message}")
        extra = {"ctx": ctx}
        if code:
            extra["event_code"] = code
        self.logger.log(level, message, exc_info=(type(error), error, error.__traceback__) if error else None,
                        extra=extra)

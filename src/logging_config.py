"""Structured logging configuration for BuoyCast.

Uses structlog's stdlib bridge so all existing ``logging.getLogger(__name__)``
calls gain structured output without any change to individual modules.

Two rendering modes:
  - Console (default): human-readable colored output via structlog ConsoleRenderer
  - JSON (json_logs=True): one JSON object per line, suitable for log aggregators

A rotating file handler (10 MB × 5 backups) is added when ``log_dir`` is set.

Log-level conventions
---------------------
  src.*           INFO   — application events worth knowing about
  bleak           WARNING — BLE scanning is extremely chatty at DEBUG/INFO
  uvicorn.access  WARNING — per-request HTTP lines clutter the output
  httpx           WARNING — request/response headers at INFO are noisy
  aiosqlite       WARNING — SQL tracing belongs in debug sessions only
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

import structlog

# Third-party loggers that should be quietened to WARNING in normal operation.
_NOISY_LOGGERS = (
    "bleak",
    "uvicorn.access",
    "httpx",
    "aiosqlite",
)


def configure_logging(
    level: str = "INFO",
    log_dir: str | None = None,
    json_logs: bool = False,
) -> None:
    """Configure structlog + stdlib logging for the whole application.

    Call once at process startup before any loggers are used.

    Args:
        level:     Root log level string, e.g. ``"INFO"`` or ``"DEBUG"``.
        log_dir:   Directory for the rotating log file.  ``None`` disables
                   file logging (useful in tests).
        json_logs: Render log records as JSON instead of the colored console
                   format.  Enable in production for log-aggregator ingestion.
    """
    # ------------------------------------------------------------------
    # Shared processors applied to every log record (stdlib and native)
    # ------------------------------------------------------------------
    shared_processors: list[structlog.types.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]

    # ------------------------------------------------------------------
    # Build the ProcessorFormatter (stdlib → structlog bridge)
    # ------------------------------------------------------------------
    if json_logs:
        final_processors: list[structlog.types.Processor] = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ]
    else:
        final_processors = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(),
        ]

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=final_processors,
        foreign_pre_chain=shared_processors,
    )

    # ------------------------------------------------------------------
    # Root logger: clear any existing handlers, then add ours
    # ------------------------------------------------------------------
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    # Console handler (always present)
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Rotating file handler (optional)
    if log_dir is not None:
        log_path = Path(log_dir) / "buoycast.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB per file
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # ------------------------------------------------------------------
    # Suppress noisy third-party loggers
    # ------------------------------------------------------------------
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # ------------------------------------------------------------------
    # Configure structlog native loggers (for future use in new modules)
    # ------------------------------------------------------------------
    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

"""Unit tests for structured logging configuration."""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from io import StringIO
from pathlib import Path

import pytest
import structlog

from src.logging_config import _NOISY_LOGGERS, configure_logging


@pytest.fixture(autouse=True)
def reset_logging():
    """Restore logging state after each test."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    original_structlog = structlog.get_config().copy()
    yield
    # Close any handlers added during the test before restoring
    for h in root.handlers:
        if h not in original_handlers:
            h.close()
    root.handlers[:] = original_handlers
    root.setLevel(original_level)
    structlog.reset_defaults()
    structlog.configure(**original_structlog)


class TestConfigureLogging:
    def test_sets_root_level(self):
        configure_logging(level="WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_debug_level(self):
        configure_logging(level="DEBUG")
        assert logging.getLogger().level == logging.DEBUG

    def test_adds_console_handler(self):
        configure_logging()
        root = logging.getLogger()
        stream_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(stream_handlers) == 1

    def test_console_handler_writes_to_stderr(self):
        configure_logging()
        root = logging.getLogger()
        stream_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert stream_handlers[0].stream is sys.stderr

    def test_no_file_handler_when_log_dir_none(self):
        configure_logging(log_dir=None)
        root = logging.getLogger()
        rotating = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(rotating) == 0

    def test_adds_rotating_file_handler(self, tmp_path):
        configure_logging(log_dir=str(tmp_path))
        root = logging.getLogger()
        rotating = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(rotating) == 1

    def test_rotating_file_created_in_log_dir(self, tmp_path):
        configure_logging(log_dir=str(tmp_path))
        log_file = tmp_path / "buoycast.log"
        # File may not exist until a record is written; check handler path
        root = logging.getLogger()
        rotating = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert Path(rotating[0].baseFilename) == log_file

    def test_rotating_file_max_bytes(self, tmp_path):
        configure_logging(log_dir=str(tmp_path))
        root = logging.getLogger()
        rotating = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert rotating[0].maxBytes == 10 * 1024 * 1024

    def test_rotating_file_backup_count(self, tmp_path):
        configure_logging(log_dir=str(tmp_path))
        root = logging.getLogger()
        rotating = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert rotating[0].backupCount == 5

    def test_clears_existing_handlers(self):
        # Add a dummy handler before configure
        dummy = logging.StreamHandler(StringIO())
        logging.getLogger().addHandler(dummy)
        configure_logging()
        assert dummy not in logging.getLogger().handlers

    def test_idempotent_on_repeated_calls(self):
        configure_logging()
        configure_logging()
        root = logging.getLogger()
        stream_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        # Second call clears and re-adds — should still be exactly one
        assert len(stream_handlers) == 1


class TestNoisyLoggerLevels:
    def test_noisy_loggers_suppressed_to_warning(self):
        configure_logging(level="DEBUG")  # root at DEBUG
        for name in _NOISY_LOGGERS:
            effective = logging.getLogger(name).level
            assert effective == logging.WARNING, (
                f"{name} should be WARNING, got {logging.getLevelName(effective)}"
            )

    def test_src_loggers_inherit_root_level(self):
        configure_logging(level="INFO")
        # src.* loggers have no explicit level set — they inherit root
        assert logging.getLogger("src.s4.reader").getEffectiveLevel() == logging.INFO
        assert logging.getLogger("src.ble.tickr").getEffectiveLevel() == logging.INFO


class TestJsonOutput:
    def test_json_mode_emits_valid_json(self):
        buf = StringIO()
        configure_logging(json_logs=True)
        # Replace stderr handler with our buffer
        root = logging.getLogger()
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(
                h, logging.handlers.RotatingFileHandler
            ):
                h.stream = buf
        logging.getLogger("test.json").info("hello structured world")
        output = buf.getvalue().strip()
        assert output, "No output produced"
        record = json.loads(output)
        assert record["event"] == "hello structured world"
        assert record["level"] == "info"
        assert "timestamp" in record

    def test_json_mode_includes_logger_name(self):
        buf = StringIO()
        configure_logging(json_logs=True)
        root = logging.getLogger()
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(
                h, logging.handlers.RotatingFileHandler
            ):
                h.stream = buf
        logging.getLogger("src.merger").warning("merge lag detected")
        record = json.loads(buf.getvalue().strip())
        assert record["logger"] == "src.merger"


class TestConsoleOutput:
    def test_console_mode_emits_text(self):
        buf = StringIO()
        configure_logging(json_logs=False)
        root = logging.getLogger()
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(
                h, logging.handlers.RotatingFileHandler
            ):
                h.stream = buf
        logging.getLogger("src.s4.reader").info("S4 connected")
        output = buf.getvalue()
        assert "S4 connected" in output

    def test_console_mode_is_not_json(self):
        buf = StringIO()
        configure_logging(json_logs=False)
        root = logging.getLogger()
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(
                h, logging.handlers.RotatingFileHandler
            ):
                h.stream = buf
        logging.getLogger("src.s4.reader").info("S4 connected")
        output = buf.getvalue().strip()
        with pytest.raises(json.JSONDecodeError):
            json.loads(output)

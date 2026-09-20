"""Small, allowlisted JSON application logs without request or credential payloads."""

import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str | int] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        error_type = getattr(record, "error_type", None)
        if isinstance(error_type, str):
            payload["error_type"] = error_type
        for key in ("source", "run_id", "phase", "status", "snapshot_id"):
            value = getattr(record, key, None)
            if isinstance(value, str) and len(value) <= 128:
                payload[key] = value
        elapsed = getattr(record, "elapsed_seconds", None)
        if type(elapsed) is int and elapsed >= 0:
            payload["elapsed_seconds"] = elapsed
        return json.dumps(payload)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("watergeo")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False

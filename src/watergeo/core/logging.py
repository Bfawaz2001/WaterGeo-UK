"""Small, allowlisted JSON application logs without request or credential payloads."""

import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        error_type = getattr(record, "error_type", None)
        if isinstance(error_type, str):
            payload["error_type"] = error_type
        return json.dumps(payload)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("watergeo")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False

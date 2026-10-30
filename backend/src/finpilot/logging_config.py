"""Structured logging with secret redaction (SEC-08).

Log records are redacted both for sensitive key/value pairs and bearer tokens.
Production emits JSON; development emits readable text. Neither format may ever
include passwords, API keys, tokens, session ids or reset tokens.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from typing import IO, Any

from .config import AppEnv, Settings

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "secret_key",
        "api_key",
        "apikey",
        "token",
        "access_token",
        "refresh_token",
        "reset_token",
        "session",
        "session_id",
        "authorization",
        "cookie",
        "set-cookie",
    }
)

_KV_PATTERN = re.compile(
    r"""(?ix)
    \b(
        authorization|api[_-]?key|secret(?:[_-]?key)?|token|access[_-]?token|
        refresh[_-]?token|reset[_-]?token|password|passwd|pwd|session[_-]?id|cookie
    )\b
    (\s*[:=]\s*)
    ("?[^\s,;"'}\]&]+"?)
    """
)

_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]+=*")

_RESERVED_RECORD_KEYS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {
    "message",
    "asctime",
    "taskName",
}


def redact_text(text: str) -> str:
    """Return ``text`` with sensitive values replaced by ``[REDACTED]``."""

    if not isinstance(text, str):
        return text
    text = _BEARER_PATTERN.sub(f"Bearer {REDACTED}", text)
    text = _KV_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    return text


class RedactingFormatter(logging.Formatter):
    """Human-readable formatter that redacts the final rendered line."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


class JsonFormatter(logging.Formatter):
    """JSON formatter that redacts message, exception and extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))

        for key, value in vars(record).items():
            if key in _RESERVED_RECORD_KEYS or key.startswith("_"):
                continue
            if key.lower() in _SENSITIVE_KEYS:
                payload[key] = REDACTED
            else:
                payload[key] = redact_text(str(value))

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings, stream: IO[str] | None = None) -> None:
    """Configure the root logger for the current environment."""

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(stream or sys.stdout)

    if settings.app_env is AppEnv.production:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root.addHandler(handler)
    root.setLevel(level)

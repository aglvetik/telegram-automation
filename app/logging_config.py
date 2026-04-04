from __future__ import annotations

import logging


class ContextFormatter(logging.Formatter):
    """Formatter that appends a small set of structured context fields."""

    context_keys = (
        "chat_id",
        "user_id",
        "message_id",
        "reason",
        "session_path",
        "lock_path",
        "status_code",
    )

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        context_parts = []
        for key in self.context_keys:
            if hasattr(record, key):
                context_parts.append(f"{key}={getattr(record, key)}")

        if not context_parts:
            return base
        return f"{base} | {' '.join(context_parts)}"


def configure_logging(level_name: str) -> None:
    """Configure application logging once at startup."""

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, level_name.upper(), logging.INFO))

    handler = logging.StreamHandler()
    formatter = ContextFormatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telethon").setLevel(logging.INFO)

from __future__ import annotations

import time
from typing import Callable


class RecentMessageGuard:
    """Deduplicates recently processed Telegram messages in memory."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_entries: int = 10_000,
        now_provider: Callable[[], float] | None = None,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._now_provider = now_provider or time.monotonic
        self._entries: dict[tuple[int, int], float] = {}

    def mark_seen(self, chat_id: int, message_id: int) -> bool:
        """Return True if the message was seen recently, otherwise remember it."""

        now = self._now_provider()
        self._prune(now)

        key = (chat_id, message_id)
        expires_at = self._entries.get(key)
        if expires_at is not None and expires_at > now:
            return True

        self._entries[key] = now + self._ttl_seconds
        return False

    def _prune(self, now: float) -> None:
        self._entries = {
            key: expires_at for key, expires_at in self._entries.items() if expires_at > now
        }
        if len(self._entries) <= self._max_entries:
            return

        sorted_items = sorted(self._entries.items(), key=lambda item: item[1], reverse=True)
        self._entries = dict(sorted_items[: self._max_entries])

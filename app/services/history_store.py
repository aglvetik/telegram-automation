from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal, TypedDict


MessageRole = Literal["user", "assistant"]


class HistoryMessage(TypedDict):
    role: MessageRole
    content: str


@dataclass(frozen=True, slots=True)
class StoredHistoryEntry:
    """Single stored message entry with an absolute timestamp."""

    timestamp: datetime
    role: MessageRole
    content: str


class InMemoryHistoryStore:
    """TTL-based in-memory conversation store keyed by chat and sender."""

    def __init__(
        self,
        *,
        message_limit: int,
        ttl_seconds: int,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._message_limit = message_limit
        self._ttl = timedelta(seconds=ttl_seconds)
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._store: dict[tuple[int, int], list[StoredHistoryEntry]] = {}

    def append(self, chat_id: int, user_id: int, role: MessageRole, content: str) -> None:
        """Append a message to short-term history for one chat and one sender."""

        if not content:
            return

        key = (chat_id, user_id)
        history = self._prune_entries(self._store.get(key, []))
        history.append(
            StoredHistoryEntry(
                timestamp=self._now_provider(),
                role=role,
                content=content,
            )
        )
        self._store[key] = history[-self._message_limit :]

    def get_messages(self, chat_id: int, user_id: int) -> list[HistoryMessage]:
        """Return current pruned history as LLM-friendly message dicts."""

        key = (chat_id, user_id)
        history = self._prune_entries(self._store.get(key, []))
        if history:
            self._store[key] = history
        else:
            self._store.pop(key, None)

        return [{"role": entry.role, "content": entry.content} for entry in history]

    def _prune_entries(self, entries: list[StoredHistoryEntry]) -> list[StoredHistoryEntry]:
        cutoff = self._now_provider() - self._ttl
        fresh_entries = [entry for entry in entries if entry.timestamp >= cutoff]
        return fresh_entries[-self._message_limit :]

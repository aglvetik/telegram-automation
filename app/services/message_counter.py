from __future__ import annotations


class MessageCounterStore:
    """Tracks per-chat message counters used by the group threshold rule."""

    def __init__(self) -> None:
        self._counters: dict[int, int] = {}

    def get(self, chat_id: int) -> int:
        """Return the current counter value for a chat."""

        return self._counters.get(chat_id, 0)

    def increment(self, chat_id: int) -> int:
        """Increase a chat counter and return the new value."""

        value = self.get(chat_id) + 1
        self._counters[chat_id] = value
        return value

    def reset(self, chat_id: int) -> None:
        """Reset a chat counter to zero."""

        self._counters[chat_id] = 0

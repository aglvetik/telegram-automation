from __future__ import annotations


class ChatStateStore:
    """Stores per-chat enable or disable state with a default-enabled policy."""

    def __init__(self) -> None:
        self._states: dict[int, bool] = {}

    def is_enabled(self, chat_id: int) -> bool:
        """Return whether automation is enabled for the given chat."""

        return self._states.get(chat_id, True)

    def set_enabled(self, chat_id: int, enabled: bool) -> None:
        """Set chat automation state explicitly."""

        self._states[chat_id] = enabled

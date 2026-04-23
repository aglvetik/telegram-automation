from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chat_states (
    chat_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    updated_at TEXT NOT NULL
);
"""

UPSERT_SQL = """
INSERT INTO chat_states (chat_id, enabled, updated_at)
VALUES (?, ?, ?)
ON CONFLICT(chat_id) DO UPDATE SET
    enabled = excluded.enabled,
    updated_at = excluded.updated_at;
"""

SELECT_ENABLED_SQL = "SELECT enabled FROM chat_states WHERE chat_id = ?;"
COUNT_STATES_SQL = "SELECT COUNT(*) FROM chat_states;"


class ChatStateStore:
    """SQLite-backed per-chat enabled/disabled state store.

    Unknown chats are enabled by default. Known chats are read from SQLite for
    every decision, so the database remains the source of truth across restarts.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.db_path,
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )
        self._configure_connection()
        self._initialize_schema()

    def is_enabled(self, chat_id: int) -> bool:
        """Return whether automation is enabled for the given chat."""

        with self._lock:
            row = self._connection.execute(SELECT_ENABLED_SQL, (chat_id,)).fetchone()
        if row is None:
            return True
        return bool(row[0])

    def set_enabled(self, chat_id: int, enabled: bool) -> None:
        """Persist chat automation state immediately."""

        updated_at = datetime.now(UTC).isoformat()
        with self._lock:
            self._connection.execute(
                UPSERT_SQL,
                (chat_id, int(enabled), updated_at),
            )

    def count_persisted_states(self) -> int:
        """Return the number of chats with explicitly persisted state."""

        with self._lock:
            row = self._connection.execute(COUNT_STATES_SQL).fetchone()
        return int(row[0])

    def close(self) -> None:
        """Close the SQLite connection."""

        with self._lock:
            self._connection.close()

    def __enter__(self) -> "ChatStateStore":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _configure_connection(self) -> None:
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL;")
            self._connection.execute("PRAGMA synchronous=NORMAL;")
            self._connection.execute("PRAGMA busy_timeout=30000;")

    def _initialize_schema(self) -> None:
        with self._lock:
            self._connection.executescript(SCHEMA_SQL)

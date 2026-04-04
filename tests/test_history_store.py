from datetime import datetime, timedelta, timezone

from app.services.history_store import InMemoryHistoryStore


def test_history_store_prunes_expired_messages() -> None:
    current_time = [datetime(2024, 1, 1, tzinfo=timezone.utc)]

    def now() -> datetime:
        return current_time[0]

    store = InMemoryHistoryStore(message_limit=10, ttl_seconds=5, now_provider=now)
    store.append(1, 2, "user", "first")

    current_time[0] += timedelta(seconds=6)
    store.append(1, 2, "assistant", "second")

    assert store.get_messages(1, 2) == [{"role": "assistant", "content": "second"}]


def test_history_store_caps_message_count() -> None:
    store = InMemoryHistoryStore(message_limit=2, ttl_seconds=60)
    store.append(1, 2, "user", "one")
    store.append(1, 2, "assistant", "two")
    store.append(1, 2, "user", "three")

    assert store.get_messages(1, 2) == [
        {"role": "assistant", "content": "two"},
        {"role": "user", "content": "three"},
    ]

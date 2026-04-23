from app.services.chat_state import ChatStateStore


def test_chat_state_defaults_to_enabled(tmp_path) -> None:
    store = ChatStateStore(tmp_path / "chat_state.sqlite3")

    try:
        assert store.is_enabled(123) is True
    finally:
        store.close()


def test_chat_state_persists_disabled_state_across_instances(tmp_path) -> None:
    db_path = tmp_path / "chat_state.sqlite3"
    first_store = ChatStateStore(db_path)

    try:
        first_store.set_enabled(123, False)
    finally:
        first_store.close()

    second_store = ChatStateStore(db_path)
    try:
        assert second_store.is_enabled(123) is False
    finally:
        second_store.close()


def test_chat_state_persists_reenabled_state_across_instances(tmp_path) -> None:
    db_path = tmp_path / "chat_state.sqlite3"
    first_store = ChatStateStore(db_path)

    try:
        first_store.set_enabled(123, False)
        first_store.set_enabled(123, True)
    finally:
        first_store.close()

    second_store = ChatStateStore(db_path)
    try:
        assert second_store.is_enabled(123) is True
    finally:
        second_store.close()

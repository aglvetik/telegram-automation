from __future__ import annotations

import logging
import shutil
from pathlib import Path

from telethon import TelegramClient

from app.config import Settings

logger = logging.getLogger(__name__)


def prepare_session_path(settings: Settings) -> tuple[str, Path]:
    """Create the session directory and migrate a legacy root session if needed."""

    session_dir = settings.telegram_session_dir
    session_dir.mkdir(parents=True, exist_ok=True)

    session_base_path = session_dir / settings.telegram_session_name
    session_file_path = settings.session_file_path
    _migrate_legacy_session_files(settings, session_file_path)
    logger.info("Using Telethon session file", extra={"session_path": str(session_file_path)})
    return str(session_base_path), session_file_path


def build_telegram_client(settings: Settings, session_reference: str) -> TelegramClient:
    """Build a TelegramClient configured for long-lived VPS use."""

    client = TelegramClient(
        session=session_reference,
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        sequential_updates=True,
        auto_reconnect=True,
        request_retries=3,
        connection_retries=-1,
        retry_delay=5,
        flood_sleep_threshold=60,
    )
    client.parse_mode = None
    return client


def _migrate_legacy_session_files(settings: Settings, target_session_file: Path) -> None:
    legacy_prefix = Path.cwd() / settings.telegram_session_name
    target_prefix = settings.telegram_session_dir / settings.telegram_session_name

    if legacy_prefix.resolve() == target_prefix.resolve():
        return

    for suffix in (".session", ".session-journal", ".session-shm", ".session-wal"):
        source = Path(f"{legacy_prefix}{suffix}")
        target = Path(f"{target_prefix}{suffix}")
        if not source.exists() or target.exists():
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        logger.info(
            "Migrated legacy Telethon session file to dedicated session dir",
            extra={"session_path": str(target)},
        )

    if target_session_file.exists():
        logger.debug("Telethon session file is present", extra={"session_path": str(target_session_file)})

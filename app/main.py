from __future__ import annotations

import asyncio
import logging
import sys

from app.config import ConfigError, Settings
from app.logging_config import configure_logging
from app.runtime import ApplicationRuntime
from app.utils.locking import DuplicateInstanceError


async def main() -> int:
    """Async application entrypoint."""

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    try:
        await ApplicationRuntime(settings).run()
    except DuplicateInstanceError as exc:
        logger.error("%s", exc, extra={"lock_path": str(settings.lock_file_path)})
        return 1
    except Exception:
        logger.exception("Service terminated with an unrecoverable error")
        return 1

    return 0


def cli() -> None:
    """Synchronous wrapper for `python -m app.main` and `python main.py`."""

    raise SystemExit(asyncio.run(main()))


if __name__ == "__main__":
    cli()

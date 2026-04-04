from __future__ import annotations

import asyncio
import logging
import signal
import sqlite3
from contextlib import suppress

import httpx
from telethon import TelegramClient
from telethon.errors import AuthKeyDuplicatedError, RPCError

from app.config import Settings
from app.services.chat_state import ChatStateStore
from app.services.content_filter import DangerousContentFilter
from app.services.history_store import InMemoryHistoryStore
from app.services.llm import ChatCompletionService
from app.services.message_counter import MessageCounterStore
from app.services.recent_messages import RecentMessageGuard
from app.telegram.client import build_telegram_client, prepare_session_path
from app.telegram.handlers import TelegramEventHandler
from app.utils.locking import SingleInstanceLock

logger = logging.getLogger(__name__)


class ApplicationRuntime:
    """Orchestrates startup, shutdown, and long-lived service resources."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._shutdown_event = asyncio.Event()
        self._registered_signals: list[signal.Signals] = []

    async def run(self) -> None:
        """Run the Telegram automation service until shutdown."""

        with SingleInstanceLock(self._settings.lock_file_path):
            logger.info(
                "Acquired single-instance lock",
                extra={"lock_path": str(self._settings.lock_file_path)},
            )
            session_reference, session_file_path = prepare_session_path(self._settings)
            logger.info(
                "Starting Telegram automation service",
                extra={"session_path": str(session_file_path)},
            )
            logger.info("Runtime configuration: %s", self._settings.redacted_summary())
            timeout = httpx.Timeout(
                timeout=self._settings.http_timeout_seconds,
                connect=self._settings.http_connect_timeout_seconds,
            )

            async with httpx.AsyncClient(timeout=timeout) as http_client:
                llm_service = ChatCompletionService(self._settings, http_client)
                handler = TelegramEventHandler(
                    settings=self._settings,
                    llm_service=llm_service,
                    history_store=InMemoryHistoryStore(
                        message_limit=self._settings.message_limit,
                        ttl_seconds=self._settings.memory_ttl_seconds,
                    ),
                    chat_state_store=ChatStateStore(),
                    counter_store=MessageCounterStore(),
                    content_filter=DangerousContentFilter(self._settings.dangerous_words),
                    recent_message_guard=RecentMessageGuard(
                        ttl_seconds=self._settings.recent_message_ttl_seconds
                    ),
                )
                client = build_telegram_client(self._settings, session_reference)
                handler.register(client)

                self._install_signal_handlers()
                try:
                    await self._run_client(client)
                finally:
                    self._remove_signal_handlers()

    async def _run_client(self, client: TelegramClient) -> None:
        async with client:
            await self._start_client(client)
            me = await client.get_me()
            logger.info(
                "Telegram client authorized",
                extra={"user_id": getattr(me, "id", 0)},
            )
            await self._wait_for_shutdown(client)

    async def _start_client(self, client: TelegramClient) -> None:
        try:
            await client.start()
        except EOFError as exc:
            raise RuntimeError(
                "Interactive Telegram login is required. Run the app manually once in a shell "
                "to create the session before using systemd."
            ) from exc
        except AuthKeyDuplicatedError as exc:
            raise RuntimeError(
                "Telegram rejected the current session because it appears to be used elsewhere. "
                "Stop other instances and recreate the session if necessary."
            ) from exc
        except sqlite3.OperationalError as exc:
            raise RuntimeError(
                "Telethon could not open the session database. This usually means another "
                "process already has the same session open."
            ) from exc
        except RPCError as exc:
            raise RuntimeError(f"Failed to start Telegram client: {exc}") from exc

        if not await client.is_user_authorized():
            raise RuntimeError(
                "Telegram session is not authorized. Run the service manually once to log in."
            )

    async def _wait_for_shutdown(self, client: TelegramClient) -> None:
        shutdown_task = asyncio.create_task(self._shutdown_event.wait(), name="shutdown-wait")

        try:
            done, _ = await asyncio.wait(
                {shutdown_task, client.disconnected},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if shutdown_task in done and self._shutdown_event.is_set():
                logger.info("Shutdown signal received, disconnecting Telegram client")
                await client.disconnect()
                await client.disconnected
                return

            logger.warning("Telegram client disconnected unexpectedly")
            raise RuntimeError(
                "Telegram client disconnected unexpectedly; the service should be restarted."
            )
        finally:
            shutdown_task.cancel()
            with suppress(asyncio.CancelledError):
                await shutdown_task

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()

        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signum, self._shutdown_event.set)
                self._registered_signals.append(signum)
            except NotImplementedError:
                signal.signal(signum, lambda *_args: self._shutdown_event.set())

    def _remove_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for signum in self._registered_signals:
            loop.remove_signal_handler(signum)
        self._registered_signals.clear()

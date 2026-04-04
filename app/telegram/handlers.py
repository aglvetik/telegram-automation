from __future__ import annotations

import asyncio
import logging

from telethon import TelegramClient, events
from telethon.errors import RPCError

from app.config import Settings
from app.services.chat_state import ChatStateStore
from app.services.content_filter import DangerousContentFilter
from app.services.history_store import InMemoryHistoryStore
from app.services.llm import ChatCompletionService
from app.services.message_counter import MessageCounterStore
from app.services.recent_messages import RecentMessageGuard
from app.services.reply_policy import ReplyFacts, decide_reply, parse_self_command

logger = logging.getLogger(__name__)


class TelegramEventHandler:
    """Thin Telethon event handler that delegates decisions to small services."""

    def __init__(
        self,
        *,
        settings: Settings,
        llm_service: ChatCompletionService,
        history_store: InMemoryHistoryStore,
        chat_state_store: ChatStateStore,
        counter_store: MessageCounterStore,
        content_filter: DangerousContentFilter,
        recent_message_guard: RecentMessageGuard,
    ) -> None:
        self._settings = settings
        self._llm_service = llm_service
        self._history_store = history_store
        self._chat_state_store = chat_state_store
        self._counter_store = counter_store
        self._content_filter = content_filter
        self._recent_message_guard = recent_message_guard

    def register(self, client: TelegramClient) -> None:
        """Register Telethon handlers on the provided client."""

        client.add_event_handler(self.on_new_message, events.NewMessage)

    async def on_new_message(self, event: events.NewMessage.Event) -> None:
        """Process a single Telegram new-message event."""

        chat_id = event.chat_id
        message_id = getattr(event.message, "id", None)
        if chat_id is None or message_id is None:
            logger.debug("Skipping message without chat_id or message_id")
            return

        if self._recent_message_guard.mark_seen(chat_id, message_id):
            logger.debug(
                "Skipping duplicate message event",
                extra={"chat_id": chat_id, "message_id": message_id},
            )
            return

        text = self._extract_text(event)
        command = parse_self_command(
            text,
            is_outgoing=bool(event.out),
            commands_enabled=self._settings.enable_self_commands,
        )
        if command is not None:
            await self._handle_self_command(event, chat_id, command)
            return

        if event.out:
            return

        if not self._chat_state_store.is_enabled(chat_id):
            logger.debug("Chat is disabled; skipping message", extra={"chat_id": chat_id})
            return

        counter_value = self._counter_store.increment(chat_id)
        is_group = bool(event.is_group or getattr(event.chat, "megagroup", False))
        reply_to_self = await self._is_reply_to_self(event, chat_id, message_id)

        decision = decide_reply(
            ReplyFacts(
                is_outgoing=bool(event.out),
                is_private=bool(event.is_private),
                is_group=is_group,
                chat_enabled=True,
                mentioned=bool(getattr(event.message, "mentioned", False)),
                explicit_mention=self._settings.primary_mention.lower() in text.lower(),
                reply_to_self=reply_to_self,
                counter_value=counter_value,
                counter_threshold=self._settings.group_reply_counter_threshold,
            )
        )
        if not decision.should_reply:
            logger.debug(
                "Message is not eligible for reply",
                extra={"chat_id": chat_id, "message_id": message_id, "reason": decision.reason},
            )
            return

        user_id = event.sender_id or 0
        match = self._content_filter.find_match(text)
        if match is not None:
            reply_text = self._settings.dangerous_reply
            logger.info(
                "Blocked dangerous message and used fixed reply",
                extra={"chat_id": chat_id, "user_id": user_id, "reason": match.keyword},
            )
        else:
            history = self._history_store.get_messages(chat_id, user_id)
            reply_text = await self._llm_service.generate_reply(
                history,
                text,
                chat_id=chat_id,
                user_id=user_id,
            )

        self._history_store.append(chat_id, user_id, "user", text)

        try:
            await event.reply(reply_text)
        except (RPCError, OSError, asyncio.TimeoutError) as exc:
            logger.exception(
                "Failed to send Telegram reply: %s",
                exc,
                extra={"chat_id": chat_id, "user_id": user_id, "message_id": message_id},
            )
            return

        self._history_store.append(chat_id, user_id, "assistant", reply_text)
        self._counter_store.reset(chat_id)
        logger.info(
            "Reply sent",
            extra={"chat_id": chat_id, "user_id": user_id, "message_id": message_id},
        )

    async def _is_reply_to_self(
        self,
        event: events.NewMessage.Event,
        chat_id: int,
        message_id: int,
    ) -> bool:
        if not event.is_reply:
            return False

        try:
            reply_message = await event.get_reply_message()
        except (RPCError, OSError, asyncio.TimeoutError) as exc:
            logger.warning(
                "Failed to inspect replied-to message: %s",
                exc,
                extra={"chat_id": chat_id, "message_id": message_id},
            )
            return False

        return bool(reply_message and reply_message.out)

    async def _handle_self_command(
        self,
        event: events.NewMessage.Event,
        chat_id: int,
        command: str,
    ) -> None:
        if command == "stop":
            self._chat_state_store.set_enabled(chat_id, False)
            self._counter_store.reset(chat_id)
            response_text = "ок, молчу тут"
        else:
            self._chat_state_store.set_enabled(chat_id, True)
            response_text = "ок, снова тут"

        logger.info(
            "Processed self-command",
            extra={"chat_id": chat_id, "reason": command},
        )

        try:
            await event.reply(response_text)
        except (RPCError, OSError, asyncio.TimeoutError) as exc:
            logger.warning(
                "Failed to send self-command confirmation: %s",
                exc,
                extra={"chat_id": chat_id, "reason": command},
            )

    @staticmethod
    def _extract_text(event: events.NewMessage.Event) -> str:
        raw_text = (event.raw_text or "").strip()
        if raw_text:
            return raw_text
        if event.message and event.message.media:
            return "[media message]"
        return "[empty message]"

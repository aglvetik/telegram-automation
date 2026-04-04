from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CommandAction = Literal["start", "stop"]


@dataclass(frozen=True, slots=True)
class ReplyFacts:
    """Pure message facts needed to decide reply eligibility."""

    is_outgoing: bool
    is_private: bool
    is_group: bool
    chat_enabled: bool
    mentioned: bool
    explicit_mention: bool
    reply_to_self: bool
    counter_value: int
    counter_threshold: int


@dataclass(frozen=True, slots=True)
class ReplyDecision:
    """Result of pure reply eligibility evaluation."""

    should_reply: bool
    reason: str


def parse_self_command(
    text: str,
    *,
    is_outgoing: bool,
    commands_enabled: bool,
) -> CommandAction | None:
    """Parse an outgoing self-command if command handling is enabled."""

    if not commands_enabled or not is_outgoing:
        return None

    normalized = text.strip().lower()
    if normalized == "!start":
        return "start"
    if normalized == "!stop":
        return "stop"
    return None


def decide_reply(facts: ReplyFacts) -> ReplyDecision:
    """Return whether the current message is eligible for an automated reply."""

    if facts.is_outgoing:
        return ReplyDecision(False, "outgoing_message")
    if not facts.chat_enabled:
        return ReplyDecision(False, "chat_disabled")
    if facts.is_private:
        return ReplyDecision(True, "private_chat")
    if not facts.is_group:
        return ReplyDecision(False, "unsupported_chat_type")
    if facts.mentioned:
        return ReplyDecision(True, "telegram_mention")
    if facts.explicit_mention:
        return ReplyDecision(True, "explicit_mention")
    if facts.reply_to_self:
        return ReplyDecision(True, "reply_to_self")
    if facts.counter_value >= facts.counter_threshold:
        return ReplyDecision(True, "message_counter_threshold")
    return ReplyDecision(False, "group_conditions_not_met")

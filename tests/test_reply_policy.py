from app.services.reply_policy import ReplyFacts, decide_reply, parse_self_command


def test_private_chat_is_always_eligible() -> None:
    decision = decide_reply(
        ReplyFacts(
            is_outgoing=False,
            is_private=True,
            is_group=False,
            chat_enabled=True,
            mentioned=False,
            explicit_mention=False,
            reply_to_self=False,
            counter_value=0,
            counter_threshold=100,
        )
    )

    assert decision.should_reply is True
    assert decision.reason == "private_chat"


def test_group_requires_trigger_until_threshold() -> None:
    decision = decide_reply(
        ReplyFacts(
            is_outgoing=False,
            is_private=False,
            is_group=True,
            chat_enabled=True,
            mentioned=False,
            explicit_mention=False,
            reply_to_self=False,
            counter_value=99,
            counter_threshold=100,
        )
    )

    assert decision.should_reply is False


def test_group_threshold_can_trigger_reply() -> None:
    decision = decide_reply(
        ReplyFacts(
            is_outgoing=False,
            is_private=False,
            is_group=True,
            chat_enabled=True,
            mentioned=False,
            explicit_mention=False,
            reply_to_self=False,
            counter_value=100,
            counter_threshold=100,
        )
    )

    assert decision.should_reply is True
    assert decision.reason == "message_counter_threshold"


def test_self_commands_only_apply_to_outgoing_messages() -> None:
    assert parse_self_command("!stop", is_outgoing=True, commands_enabled=True) == "stop"
    assert parse_self_command("!start", is_outgoing=False, commands_enabled=True) is None
    assert parse_self_command("!start", is_outgoing=True, commands_enabled=False) is None

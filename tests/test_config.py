import pytest

from app.config import ConfigError, Settings, parse_bool


def _base_env() -> dict[str, str]:
    return {
        "TELEGRAM_API_ID": "12345",
        "TELEGRAM_API_HASH": "hash-value",
        "TELEGRAM_SESSION_NAME": "main_account",
        "TELEGRAM_SESSION_DIR": "./data/sessions",
        "PRIMARY_MENTION": "@unsigned69",
        "MESSAGE_LIMIT": "30",
        "MEMORY_TTL_SECONDS": "600",
        "GROUP_REPLY_COUNTER_THRESHOLD": "100",
        "DANGEROUS_WORDS": "token,api_key,secret",
        "DANGEROUS_REPLY": "не, в это не лезу",
        "API_FALLBACK_REPLY": "че то я туплю ща",
        "DEEPSEEK_URL": "https://api.deepseek.com/chat/completions",
        "DEEPSEEK_API_KEY": "secret-key",
        "DEEPSEEK_MODEL": "deepseek-chat",
        "HTTP_TIMEOUT_SECONDS": "30",
        "HTTP_CONNECT_TIMEOUT_SECONDS": "10",
        "LOG_LEVEL": "INFO",
        "ENABLE_SELF_COMMANDS": "true",
        "SYSTEM_PROMPT": "stay casual",
    }


def test_parse_bool_accepts_expected_values() -> None:
    assert parse_bool("true", name="ENABLE_SELF_COMMANDS") is True
    assert parse_bool("0", name="ENABLE_SELF_COMMANDS") is False


def test_settings_parse_dangerous_words_and_bool() -> None:
    settings = Settings.from_mapping(_base_env())

    assert settings.enable_self_commands is True
    assert settings.dangerous_words == ("token", "api_key", "secret")


def test_settings_reject_placeholder_secrets() -> None:
    env = _base_env()
    env["DEEPSEEK_API_KEY"] = "replace_me"

    with pytest.raises(ConfigError):
        Settings.from_mapping(env)


def test_settings_reject_session_suffixes() -> None:
    env = _base_env()
    env["TELEGRAM_SESSION_NAME"] = "main_account.session"

    with pytest.raises(ConfigError):
        Settings.from_mapping(env)


def test_settings_reject_invalid_upstream_url() -> None:
    env = _base_env()
    env["DEEPSEEK_URL"] = "not-a-url"

    with pytest.raises(ConfigError):
        Settings.from_mapping(env)


def test_settings_reject_invalid_retry_delay_order() -> None:
    env = _base_env()
    env["HTTP_RETRY_BASE_DELAY_SECONDS"] = "5"
    env["HTTP_RETRY_MAX_DELAY_SECONDS"] = "1"

    with pytest.raises(ConfigError):
        Settings.from_mapping(env)

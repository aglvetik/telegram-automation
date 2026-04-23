from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from dotenv import load_dotenv


class ConfigError(ValueError):
    """Raised when runtime configuration is invalid."""


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
_PLACEHOLDER_VALUES = {"replace_me", "changeme", "change_me", "your_value_here"}
_DISALLOWED_SESSION_SUFFIXES = (
    ".session",
    ".session-journal",
    ".session-shm",
    ".session-wal",
    ".lock",
)


def _require_text(env: Mapping[str, str], name: str) -> str:
    raw_value = env.get(name)
    if raw_value is None:
        raise ConfigError(f"Missing required environment variable: {name}")

    value = raw_value.strip()
    if not value:
        raise ConfigError(f"Environment variable {name} must not be blank")
    return value


def parse_bool(raw_value: str, *, name: str) -> bool:
    """Parse a boolean environment variable safely."""

    normalized = raw_value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ConfigError(
        f"Environment variable {name} must be a boolean value "
        f"({_TRUE_VALUES | _FALSE_VALUES})"
    )


def parse_int(raw_value: str, *, name: str, minimum: int | None = None) -> int:
    """Parse an integer environment variable safely."""

    try:
        value = int(raw_value.strip())
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be an integer") from exc

    if minimum is not None and value < minimum:
        raise ConfigError(f"Environment variable {name} must be >= {minimum}")
    return value


def parse_float(raw_value: str, *, name: str, minimum: float | None = None) -> float:
    """Parse a float environment variable safely."""

    try:
        value = float(raw_value.strip())
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be a number") from exc

    if minimum is not None and value < minimum:
        raise ConfigError(f"Environment variable {name} must be >= {minimum}")
    return value


def parse_csv(raw_value: str) -> tuple[str, ...]:
    """Parse a comma-separated string into a normalized tuple."""

    items = [item.strip() for item in raw_value.split(",")]
    return tuple(item for item in items if item)


def _require_secret(env: Mapping[str, str], name: str) -> str:
    value = _require_text(env, name)
    if value.lower() in _PLACEHOLDER_VALUES:
        raise ConfigError(f"Environment variable {name} still contains a placeholder value")
    return value


def parse_http_url(raw_value: str, *, name: str) -> str:
    """Validate an HTTP(S) URL from environment configuration."""

    value = raw_value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(
            f"Environment variable {name} must be a valid absolute HTTP(S) URL"
        )
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Typed runtime configuration loaded from environment variables."""

    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_name: str
    telegram_session_dir: Path
    chat_state_db_path: Path
    primary_mention: str
    message_limit: int
    memory_ttl_seconds: int
    group_reply_counter_threshold: int
    dangerous_words: tuple[str, ...]
    dangerous_reply: str
    api_fallback_reply: str
    deepseek_url: str
    deepseek_api_key: str
    deepseek_model: str
    http_timeout_seconds: float
    http_connect_timeout_seconds: float
    http_max_retries: int
    http_retry_base_delay_seconds: float
    http_retry_max_delay_seconds: float
    log_level: str
    enable_self_commands: bool
    llm_temperature: float
    llm_max_tokens: int
    recent_message_ttl_seconds: int
    system_prompt: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from OS environment and .env file."""

        load_dotenv()
        env = {key: value for key, value in os.environ.items() if value is not None}
        return cls.from_mapping(env)

    @classmethod
    def from_mapping(cls, env: Mapping[str, str]) -> "Settings":
        """Build settings from a mapping, which also makes tests straightforward."""

        session_name = _require_text(env, "TELEGRAM_SESSION_NAME")
        if Path(session_name).name != session_name:
            raise ConfigError("TELEGRAM_SESSION_NAME must be a base filename, not a path")
        if session_name.endswith(_DISALLOWED_SESSION_SUFFIXES):
            raise ConfigError(
                "TELEGRAM_SESSION_NAME must not include session or lock file suffixes"
            )

        session_dir = Path(_require_text(env, "TELEGRAM_SESSION_DIR")).expanduser()
        if not session_dir.is_absolute():
            session_dir = (Path.cwd() / session_dir).resolve()

        chat_state_db_path = Path(env.get("CHAT_STATE_DB_PATH", "./data/chat_state.sqlite3"))
        chat_state_db_path = chat_state_db_path.expanduser()
        if not chat_state_db_path.is_absolute():
            chat_state_db_path = (Path.cwd() / chat_state_db_path).resolve()

        dangerous_words = parse_csv(_require_text(env, "DANGEROUS_WORDS"))
        if not dangerous_words:
            raise ConfigError("DANGEROUS_WORDS must contain at least one value")

        log_level = _require_text(env, "LOG_LEVEL").upper()
        if log_level not in _LOG_LEVELS:
            raise ConfigError(
                f"LOG_LEVEL must be one of {sorted(_LOG_LEVELS)}, got {log_level!r}"
            )

        http_retry_base_delay_seconds = parse_float(
            env.get("HTTP_RETRY_BASE_DELAY_SECONDS", "0.5"),
            name="HTTP_RETRY_BASE_DELAY_SECONDS",
            minimum=0.0,
        )
        http_retry_max_delay_seconds = parse_float(
            env.get("HTTP_RETRY_MAX_DELAY_SECONDS", "5.0"),
            name="HTTP_RETRY_MAX_DELAY_SECONDS",
            minimum=0.0,
        )
        if http_retry_max_delay_seconds < http_retry_base_delay_seconds:
            raise ConfigError(
                "HTTP_RETRY_MAX_DELAY_SECONDS must be >= HTTP_RETRY_BASE_DELAY_SECONDS"
            )

        return cls(
            telegram_api_id=parse_int(
                _require_text(env, "TELEGRAM_API_ID"),
                name="TELEGRAM_API_ID",
                minimum=1,
            ),
            telegram_api_hash=_require_secret(env, "TELEGRAM_API_HASH"),
            telegram_session_name=session_name,
            telegram_session_dir=session_dir,
            chat_state_db_path=chat_state_db_path,
            primary_mention=_require_text(env, "PRIMARY_MENTION"),
            message_limit=parse_int(
                _require_text(env, "MESSAGE_LIMIT"),
                name="MESSAGE_LIMIT",
                minimum=1,
            ),
            memory_ttl_seconds=parse_int(
                _require_text(env, "MEMORY_TTL_SECONDS"),
                name="MEMORY_TTL_SECONDS",
                minimum=1,
            ),
            group_reply_counter_threshold=parse_int(
                _require_text(env, "GROUP_REPLY_COUNTER_THRESHOLD"),
                name="GROUP_REPLY_COUNTER_THRESHOLD",
                minimum=1,
            ),
            dangerous_words=dangerous_words,
            dangerous_reply=_require_text(env, "DANGEROUS_REPLY"),
            api_fallback_reply=_require_text(env, "API_FALLBACK_REPLY"),
            deepseek_url=parse_http_url(
                _require_text(env, "DEEPSEEK_URL"),
                name="DEEPSEEK_URL",
            ),
            deepseek_api_key=_require_secret(env, "DEEPSEEK_API_KEY"),
            deepseek_model=_require_text(env, "DEEPSEEK_MODEL"),
            http_timeout_seconds=parse_float(
                _require_text(env, "HTTP_TIMEOUT_SECONDS"),
                name="HTTP_TIMEOUT_SECONDS",
                minimum=0.1,
            ),
            http_connect_timeout_seconds=parse_float(
                _require_text(env, "HTTP_CONNECT_TIMEOUT_SECONDS"),
                name="HTTP_CONNECT_TIMEOUT_SECONDS",
                minimum=0.1,
            ),
            http_max_retries=parse_int(
                env.get("HTTP_MAX_RETRIES", "3"),
                name="HTTP_MAX_RETRIES",
                minimum=0,
            ),
            http_retry_base_delay_seconds=http_retry_base_delay_seconds,
            http_retry_max_delay_seconds=http_retry_max_delay_seconds,
            log_level=log_level,
            enable_self_commands=parse_bool(
                _require_text(env, "ENABLE_SELF_COMMANDS"),
                name="ENABLE_SELF_COMMANDS",
            ),
            llm_temperature=parse_float(
                env.get("LLM_TEMPERATURE", "1.15"),
                name="LLM_TEMPERATURE",
                minimum=0.0,
            ),
            llm_max_tokens=parse_int(
                env.get("LLM_MAX_TOKENS", "300"),
                name="LLM_MAX_TOKENS",
                minimum=1,
            ),
            recent_message_ttl_seconds=parse_int(
                env.get("RECENT_MESSAGE_TTL_SECONDS", "900"),
                name="RECENT_MESSAGE_TTL_SECONDS",
                minimum=1,
            ),
            system_prompt=_require_text(env, "SYSTEM_PROMPT"),
        )

    @property
    def session_file_path(self) -> Path:
        """Return the exact Telethon SQLite session file path."""

        return self.telegram_session_dir / f"{self.telegram_session_name}.session"

    @property
    def lock_file_path(self) -> Path:
        """Return the process lock file path for the active session."""

        return self.telegram_session_dir / f"{self.telegram_session_name}.lock"

    def redacted_summary(self) -> dict[str, object]:
        """Return a startup-safe settings summary without secrets."""

        return {
            "telegram_api_id": self.telegram_api_id,
            "telegram_session_name": self.telegram_session_name,
            "telegram_session_dir": str(self.telegram_session_dir),
            "session_file_path": str(self.session_file_path),
            "chat_state_db_path": str(self.chat_state_db_path),
            "primary_mention": self.primary_mention,
            "message_limit": self.message_limit,
            "memory_ttl_seconds": self.memory_ttl_seconds,
            "group_reply_counter_threshold": self.group_reply_counter_threshold,
            "dangerous_words_count": len(self.dangerous_words),
            "deepseek_url": self.deepseek_url,
            "deepseek_model": self.deepseek_model,
            "http_timeout_seconds": self.http_timeout_seconds,
            "http_connect_timeout_seconds": self.http_connect_timeout_seconds,
            "http_max_retries": self.http_max_retries,
            "http_retry_base_delay_seconds": self.http_retry_base_delay_seconds,
            "http_retry_max_delay_seconds": self.http_retry_max_delay_seconds,
            "log_level": self.log_level,
            "enable_self_commands": self.enable_self_commands,
            "llm_temperature": self.llm_temperature,
            "llm_max_tokens": self.llm_max_tokens,
            "recent_message_ttl_seconds": self.recent_message_ttl_seconds,
        }

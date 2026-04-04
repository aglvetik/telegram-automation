from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Sequence

import httpx

from app.config import Settings
from app.services.history_store import HistoryMessage

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = {408, 409, 425, 429}


class ChatCompletionService:
    """HTTPX-backed client for a DeepSeek-compatible chat completions API."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http_client = http_client
        self._random = random.Random()

    @staticmethod
    def is_retryable_status(status_code: int) -> bool:
        """Return whether an HTTP status code is safe to retry."""

        return status_code in _RETRYABLE_STATUS_CODES or 500 <= status_code < 600

    @staticmethod
    def build_messages(
        *,
        system_prompt: str,
        history: Sequence[HistoryMessage],
        user_input: str,
    ) -> list[dict[str, str]]:
        """Build the request message array for the upstream chat API."""

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend({"role": item["role"], "content": item["content"]} for item in history)
        messages.append({"role": "user", "content": user_input})
        return messages

    @staticmethod
    def parse_content(payload: Any) -> str | None:
        """Extract assistant text defensively from an upstream JSON payload."""

        if not isinstance(payload, dict):
            return None

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return None

        message = first_choice.get("message")
        if not isinstance(message, dict):
            return None

        content = message.get("content")
        if not isinstance(content, str):
            return None

        stripped = content.strip()
        return stripped or None

    async def generate_reply(
        self,
        history: Sequence[HistoryMessage],
        user_input: str,
        *,
        chat_id: int,
        user_id: int,
    ) -> str:
        """Send a chat-completion request and return fallback text on failure."""

        payload = {
            "model": self._settings.deepseek_model,
            "messages": self.build_messages(
                system_prompt=self._settings.system_prompt,
                history=history,
                user_input=user_input,
            ),
            "temperature": self._settings.llm_temperature,
            "max_tokens": self._settings.llm_max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

        total_attempts = self._settings.http_max_retries + 1

        for attempt in range(1, total_attempts + 1):
            try:
                response = await self._http_client.post(
                    self._settings.deepseek_url,
                    json=payload,
                    headers=headers,
                )

                if self.is_retryable_status(response.status_code):
                    raise httpx.HTTPStatusError(
                        f"Retryable upstream failure: {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                if 400 <= response.status_code < 500:
                    logger.error(
                        "LLM request failed with permanent client error: %s",
                        response.status_code,
                        extra={
                            "chat_id": chat_id,
                            "user_id": user_id,
                            "status_code": response.status_code,
                        },
                    )
                    return self._settings.api_fallback_reply

                response.raise_for_status()
                payload_data = response.json()
                content = self.parse_content(payload_data)
                if content is not None:
                    return content

                logger.error(
                    "LLM response payload is missing assistant content",
                    extra={"chat_id": chat_id, "user_id": user_id},
                )
                return self._settings.api_fallback_reply
            except httpx.HTTPStatusError as exc:
                if attempt >= total_attempts or not self.is_retryable_status(exc.response.status_code):
                    logger.error(
                        "LLM request failed after retries: %s",
                        exc,
                        extra={
                            "chat_id": chat_id,
                            "user_id": user_id,
                            "status_code": exc.response.status_code,
                        },
                    )
                    return self._settings.api_fallback_reply

                await self._sleep_before_retry(attempt, chat_id=chat_id, user_id=user_id)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                if attempt >= total_attempts:
                    logger.error(
                        "LLM request exhausted retries after network failure: %s",
                        exc,
                        extra={"chat_id": chat_id, "user_id": user_id},
                    )
                    return self._settings.api_fallback_reply

                await self._sleep_before_retry(attempt, chat_id=chat_id, user_id=user_id)
            except ValueError as exc:
                logger.error(
                    "LLM response parsing failed: %s",
                    exc,
                    extra={"chat_id": chat_id, "user_id": user_id},
                )
                return self._settings.api_fallback_reply

        return self._settings.api_fallback_reply

    async def _sleep_before_retry(self, attempt: int, *, chat_id: int, user_id: int) -> None:
        base_delay = self._settings.http_retry_base_delay_seconds * (2 ** (attempt - 1))
        bounded_delay = min(base_delay, self._settings.http_retry_max_delay_seconds)
        jitter = self._random.uniform(0.0, max(0.1, bounded_delay * 0.25))
        delay = bounded_delay + jitter

        logger.warning(
            "Retrying LLM request after transient failure in %.2f seconds",
            delay,
            extra={"chat_id": chat_id, "user_id": user_id},
        )
        await asyncio.sleep(delay)

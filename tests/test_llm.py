from app.services.llm import ChatCompletionService


def test_parse_content_extracts_assistant_text() -> None:
    payload = {"choices": [{"message": {"content": " hello "}}]}

    assert ChatCompletionService.parse_content(payload) == "hello"


def test_retryable_status_covers_rate_limits_and_5xx() -> None:
    assert ChatCompletionService.is_retryable_status(429) is True
    assert ChatCompletionService.is_retryable_status(503) is True
    assert ChatCompletionService.is_retryable_status(401) is False

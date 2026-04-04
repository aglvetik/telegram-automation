from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class ContentMatch:
    """A matched dangerous keyword."""

    keyword: str
    matched_text: str


class DangerousContentFilter:
    """Keyword-based filter with conservative token-boundary matching."""

    def __init__(self, keywords: Sequence[str]) -> None:
        normalized = [keyword.strip() for keyword in keywords if keyword.strip()]
        self._patterns = [
            (
                keyword,
                re.compile(rf"(?<!\w){re.escape(keyword)}(?!\w)", re.IGNORECASE),
            )
            for keyword in normalized
        ]

    def find_match(self, text: str) -> ContentMatch | None:
        """Return the first matched dangerous keyword, if any."""

        for keyword, pattern in self._patterns:
            match = pattern.search(text)
            if match is not None:
                return ContentMatch(keyword=keyword, matched_text=match.group(0))
        return None

    def is_dangerous(self, text: str) -> bool:
        """Return whether the text contains a dangerous keyword."""

        return self.find_match(text) is not None

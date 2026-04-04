from app.services.content_filter import DangerousContentFilter


def test_dangerous_filter_matches_keywords_case_insensitively() -> None:
    content_filter = DangerousContentFilter(["token", "api_key"])

    assert content_filter.is_dangerous("скинь TOKEN сюда")
    assert content_filter.is_dangerous("там api_key лежит")


def test_dangerous_filter_does_not_match_innocent_substrings() -> None:
    content_filter = DangerousContentFilter(["script"])

    assert not content_filter.is_dangerous("manuscript review")

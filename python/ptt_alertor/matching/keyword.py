from __future__ import annotations

import re

REGEXP_PREFIX = "regexp:"
EXCLUDE_PREFIX = "!"
AND_SEP = "&"


def match_keyword(title: str, keyword: str) -> bool:
    """Match a single keyword/expression against a title.

    Rules (port from models/article/article.go MatchKeyword):
      - "kw1&kw2"      -> all parts must individually match (recursive)
      - "regexp:..."   -> regex search on title
      - "!kw"          -> NOT contains kw (case-insensitive)
      - else           -> case-insensitive substring contains
    """
    if not keyword:
        return False
    if AND_SEP in keyword:
        return all(match_keyword(title, part) for part in keyword.split(AND_SEP))
    if keyword.startswith(REGEXP_PREFIX):
        pattern = keyword[len(REGEXP_PREFIX):]
        try:
            return re.search(pattern, title) is not None
        except re.error:
            return False
    if keyword.startswith(EXCLUDE_PREFIX):
        excl = keyword[len(EXCLUDE_PREFIX):]
        return not _contains(title, excl)
    return _contains(title, keyword)


def match_any_keyword(title: str, keywords: list[str]) -> str | None:
    """Return the first matching keyword expression, or None."""
    for kw in keywords:
        if match_keyword(title, kw):
            return kw
    return None


def match_author(article_author: str, subscribed_author: str) -> bool:
    """Case-insensitive author match (port: EqualFold)."""
    return article_author.casefold() == subscribed_author.casefold()


def _contains(haystack: str, needle: str) -> bool:
    return needle.casefold() in haystack.casefold()

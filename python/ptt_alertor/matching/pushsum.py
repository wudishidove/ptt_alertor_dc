from __future__ import annotations

PUSH_MIN, PUSH_MAX = 1, 100
BOO_MIN, BOO_MAX = -100, -1


def parse_pushsum_value(raw: str) -> int | None:
    """Parse a number from user input. Returns None if invalid."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def is_valid_push(n: int) -> bool:
    """For 新增推文數: 0 means delete, 1..100 valid."""
    return 0 <= n <= PUSH_MAX


def is_valid_boo(n: int) -> bool:
    """For 新增噓文數: user enters 0..100; we store as negative.

    Original Go behaviour: input is positive, internally inverted to negative.
    Returns True if input is in [0, 100].
    """
    return 0 <= n <= PUSH_MAX


def hits_threshold(article_pushsum: int, up: int, down: int) -> bool:
    """Whether an article meets a user's pushsum subscription thresholds."""
    if up > 0 and article_pushsum >= up:
        return True
    if down < 0 and article_pushsum <= down:
        return True
    return False

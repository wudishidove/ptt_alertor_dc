from __future__ import annotations

DISCORD_LIMIT = 2000


def split_message(text: str, limit: int = DISCORD_LIMIT) -> list[str]:
    """Split a message into chunks <= ``limit`` characters.

    Prefers to break on newlines so URLs / titles aren't mid-cut.
    Falls back to hard slicing for lines longer than the limit.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    def _flush() -> None:
        nonlocal buf, buf_len
        if buf:
            chunks.append("\n".join(buf))
            buf = []
            buf_len = 0

    for line in text.split("\n"):
        line_len = len(line) + 1  # +1 for the newline we'd insert
        if line_len > limit:
            _flush()
            for i in range(0, len(line), limit):
                chunks.append(line[i : i + limit])
            continue

        if buf_len + line_len > limit:
            _flush()

        buf.append(line)
        buf_len += line_len

    _flush()
    return [c for c in chunks if c]

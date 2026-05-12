from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

PTT_BASE = "https://www.ptt.cc"
_ID_RE = re.compile(r"[GM]\.(\d+)\.")


def parse_article_id(link_or_code: str) -> int:
    m = _ID_RE.search(link_or_code)
    return int(m.group(1)) if m else 0


@dataclass
class Comment:
    tag: str = ""
    user_id: str = ""
    content: str = ""
    ip_datetime: str = ""
    datetime_: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "userId": self.user_id,
            "content": self.content,
            "ipDateTime": self.ip_datetime,
            "dateTime": self.datetime_.isoformat() if self.datetime_ else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Comment:
        dt_str = data.get("dateTime")
        return cls(
            tag=data.get("tag", ""),
            user_id=data.get("userId", ""),
            content=data.get("content", ""),
            ip_datetime=data.get("ipDateTime", ""),
            datetime_=datetime.fromisoformat(dt_str) if dt_str else None,
        )


@dataclass
class Article:
    id: int = 0
    code: str = ""
    title: str = ""
    link: str = ""
    date: str = ""
    author: str = ""
    push_sum: int = 0
    board: str = ""
    last_push_datetime: datetime | None = None
    comments: list[Comment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "title": self.title,
            "link": self.link,
            "date": self.date,
            "author": self.author,
            "pushSum": self.push_sum,
            "board": self.board,
            "lastPushDateTime": (
                self.last_push_datetime.isoformat() if self.last_push_datetime else None
            ),
            "comments": [c.to_dict() for c in self.comments],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Article:
        dt_str = data.get("lastPushDateTime")
        return cls(
            id=int(data.get("id", 0) or 0),
            code=data.get("code", ""),
            title=data.get("title", ""),
            link=data.get("link", ""),
            date=data.get("date", ""),
            author=data.get("author", ""),
            push_sum=int(data.get("pushSum", 0) or 0),
            board=data.get("board", ""),
            last_push_datetime=datetime.fromisoformat(dt_str) if dt_str else None,
            comments=[Comment.from_dict(c) for c in data.get("comments", [])],
        )

    def format_simple(self) -> str:
        return f"{self.title}\r\n{self.link}"

    def format_with_pushsum(self) -> str:
        prefix = format_pushsum(self.push_sum)
        return f"{prefix} {self.title}\r\n{self.link}" if prefix else f"{self.title}\r\n{self.link}"


_PUSHSUM_NUM_TEXT: dict[int, str] = {
    100: "爆",
    -10: "X1",
    -20: "X2",
    -30: "X3",
    -40: "X4",
    -50: "X5",
    -60: "X6",
    -70: "X7",
    -80: "X8",
    -90: "X9",
    -100: "XX",
}
_PUSHSUM_TEXT_NUM: dict[str, int] = {v.casefold(): k for k, v in _PUSHSUM_NUM_TEXT.items()}


def format_pushsum(n: int) -> str:
    if n in _PUSHSUM_NUM_TEXT:
        return _PUSHSUM_NUM_TEXT[n]
    if n >= 100:
        return "爆"
    if n == 0:
        return ""
    return str(n)


def parse_pushsum_text(text: str) -> int:
    """Convert PTT push count cell text to integer.

    e.g. "爆" -> 100, "X1" -> -10, "12" -> 12, "" -> 0
    """
    if not text:
        return 0
    key = text.strip().casefold()
    if key in _PUSHSUM_TEXT_NUM:
        return _PUSHSUM_TEXT_NUM[key]
    try:
        return int(text)
    except ValueError:
        return 0

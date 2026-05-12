from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PushSum:
    up: int = 0
    down: int = 0

    def is_empty(self) -> bool:
        return self.up == 0 and self.down == 0

    def to_dict(self) -> dict[str, int]:
        return {"up": self.up, "down": self.down}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PushSum:
        if not data:
            return cls()
        return cls(up=int(data.get("up", 0) or 0), down=int(data.get("down", 0) or 0))


@dataclass
class Subscription:
    board: str = ""
    keywords: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    articles: list[str] = field(default_factory=list)
    push_sum: PushSum = field(default_factory=PushSum)

    def is_empty(self) -> bool:
        return (
            not self.keywords
            and not self.authors
            and not self.articles
            and self.push_sum.is_empty()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "board": self.board,
            "keywords": list(self.keywords),
            "authors": list(self.authors),
            "articles": list(self.articles),
            "pushSum": self.push_sum.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Subscription:
        return cls(
            board=data.get("board", ""),
            keywords=list(data.get("keywords") or []),
            authors=list(data.get("authors") or []),
            articles=list(data.get("articles") or []),
            push_sum=PushSum.from_dict(data.get("pushSum")),
        )

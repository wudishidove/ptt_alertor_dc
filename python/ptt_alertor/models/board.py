from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .article import Article


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BoardSnapshot:
    board: str = ""
    last_fetched: datetime = field(default_factory=_utcnow)
    max_article_id: int = 0
    articles: list[Article] = field(default_factory=list)

    def article_ids(self) -> set[int]:
        return {a.id for a in self.articles if a.id}

    def to_dict(self) -> dict[str, Any]:
        return {
            "board": self.board,
            "lastFetched": self.last_fetched.isoformat(),
            "maxArticleId": self.max_article_id,
            "articles": [a.to_dict() for a in self.articles],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BoardSnapshot:
        ts = data.get("lastFetched")
        return cls(
            board=data.get("board", ""),
            last_fetched=datetime.fromisoformat(ts) if ts else _utcnow(),
            max_article_id=int(data.get("maxArticleId", 0) or 0),
            articles=[Article.from_dict(a) for a in (data.get("articles") or [])],
        )

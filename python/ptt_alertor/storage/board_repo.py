from __future__ import annotations

import asyncio
from pathlib import Path

from ..logger import get_logger
from ..models import Article, BoardSnapshot
from .json_store import list_json_files, read_json, write_json

log = get_logger(__name__)


class BoardRepo:
    """Per-board snapshot of recently seen articles + max id."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, BoardSnapshot] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def boards_dir(self) -> Path:
        return self.root / "boards"

    async def load_all(self) -> None:
        self.boards_dir.mkdir(parents=True, exist_ok=True)
        for path in list_json_files(self.boards_dir):
            try:
                raw = await read_json(path)
                if not raw:
                    continue
                snap = BoardSnapshot.from_dict(raw)
                if snap.board:
                    self._cache[snap.board.lower()] = snap
            except Exception as exc:
                log.exception("Failed to load board %s: %s", path, exc)
        log.info("Loaded %d board snapshots", len(self._cache))

    def _lock_for(self, board: str) -> asyncio.Lock:
        key = board.lower()
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def _path_for(self, board: str) -> Path:
        return self.boards_dir / f"{board}.json"

    def get(self, board: str) -> BoardSnapshot | None:
        return self._cache.get(board.lower())

    def get_max_id(self, board: str) -> int:
        snap = self.get(board)
        return snap.max_article_id if snap else 0

    def diff_new(self, board: str, online: list[Article]) -> list[Article]:
        """Return articles whose id is greater than the saved max id."""
        snap = self.get(board)
        existing_ids = snap.article_ids() if snap else set()
        max_id = snap.max_article_id if snap else 0
        new = [a for a in online if a.id and a.id > max_id and a.id not in existing_ids]
        return new

    async def save(self, snap: BoardSnapshot) -> None:
        key = snap.board.lower()
        if not key:
            raise ValueError("BoardSnapshot has no board name")
        self._cache[key] = snap
        async with self._lock_for(snap.board):
            await write_json(self._path_for(snap.board), snap.to_dict())

    async def update_after_fetch(self, board: str, articles: list[Article]) -> list[Article]:
        """Atomically merge online articles, return the *new* ones."""
        snap = self.get(board) or BoardSnapshot(board=board)
        max_id = snap.max_article_id
        existing_ids = snap.article_ids()
        new_articles = [
            a for a in articles if a.id and a.id > max_id and a.id not in existing_ids
        ]

        snap.articles = list(articles)
        if articles:
            snap.max_article_id = max(snap.max_article_id, max(a.id for a in articles if a.id))
        from datetime import datetime, timezone
        snap.last_fetched = datetime.now(timezone.utc)
        await self.save(snap)
        return new_articles

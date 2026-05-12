from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..logger import get_logger
from .json_store import read_json, write_json

log = get_logger(__name__)


class ArticleSubsRepo:
    """Reverse-lookup: article code -> set of subscriber channel IDs.

    Stored as one JSON file: { code: {"board": str, "subscribers": [channelID...]} }
    """

    FILENAME = "article_subs.json"

    def __init__(self, root: Path) -> None:
        self.path = root / self.FILENAME
        self._lock = asyncio.Lock()
        self._cache: dict[str, dict[str, Any]] = {}

    async def load(self) -> None:
        raw = await read_json(self.path)
        if not raw:
            self._cache = {}
            return
        self._cache = {}
        for code, entry in raw.items():
            if isinstance(entry, dict):
                self._cache[code] = {
                    "board": entry.get("board", ""),
                    "subscribers": set(entry.get("subscribers") or []),
                }
        log.info("Loaded %d article subscriptions", len(self._cache))

    async def _persist(self) -> None:
        serial = {
            code: {"board": e["board"], "subscribers": sorted(e["subscribers"])}
            for code, e in self._cache.items()
        }
        await write_json(self.path, serial)

    def codes(self) -> list[str]:
        return list(self._cache.keys())

    def board_of(self, code: str) -> str:
        entry = self._cache.get(code)
        return entry["board"] if entry else ""

    def subscribers(self, code: str) -> set[str]:
        entry = self._cache.get(code)
        return set(entry["subscribers"]) if entry else set()

    def has_subscribers(self, code: str) -> bool:
        entry = self._cache.get(code)
        return bool(entry and entry["subscribers"])

    async def add(self, code: str, board: str, channel_id: str) -> None:
        async with self._lock:
            entry = self._cache.setdefault(
                code, {"board": board, "subscribers": set()}
            )
            entry["board"] = board or entry["board"]
            entry["subscribers"].add(channel_id)
            await self._persist()

    async def remove(self, code: str, channel_id: str) -> None:
        async with self._lock:
            entry = self._cache.get(code)
            if not entry:
                return
            entry["subscribers"].discard(channel_id)
            if not entry["subscribers"]:
                self._cache.pop(code, None)
            await self._persist()

    async def remove_all(self, code: str) -> None:
        async with self._lock:
            self._cache.pop(code, None)
            await self._persist()

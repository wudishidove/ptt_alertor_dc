from __future__ import annotations

import asyncio
from pathlib import Path

from ..logger import get_logger
from .json_store import read_json, write_json

log = get_logger(__name__)


class PushsumSubsRepo:
    """Reverse-lookup: board -> set of subscriber channel IDs (any push/boo threshold).

    Stored as one JSON file: { board_lower: [channelID, ...] }
    """

    FILENAME = "pushsum_subs.json"

    def __init__(self, root: Path) -> None:
        self.path = root / self.FILENAME
        self._lock = asyncio.Lock()
        self._cache: dict[str, set[str]] = {}

    async def load(self) -> None:
        raw = await read_json(self.path)
        self._cache = {
            board: set(channels or []) for board, channels in (raw or {}).items()
        }
        log.info("Loaded pushsum subs for %d boards", len(self._cache))

    async def _persist(self) -> None:
        serial = {board: sorted(channels) for board, channels in self._cache.items() if channels}
        await write_json(self.path, serial)

    def boards(self) -> list[str]:
        return [b for b, ch in self._cache.items() if ch]

    def subscribers(self, board: str) -> set[str]:
        return set(self._cache.get(board.lower(), set()))

    async def add(self, board: str, channel_id: str) -> None:
        key = board.lower()
        async with self._lock:
            self._cache.setdefault(key, set()).add(channel_id)
            await self._persist()

    async def remove(self, board: str, channel_id: str) -> None:
        key = board.lower()
        async with self._lock:
            if key in self._cache:
                self._cache[key].discard(channel_id)
                if not self._cache[key]:
                    self._cache.pop(key)
            await self._persist()

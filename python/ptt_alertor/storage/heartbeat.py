from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from ..logger import get_logger
from .json_store import read_json, write_json

log = get_logger(__name__)


class HeartbeatStore:
    FILENAME = "heartbeat.json"

    def __init__(self, root: Path) -> None:
        self.path = root / self.FILENAME
        self._lock = asyncio.Lock()
        self._last: datetime | None = None

    async def load(self) -> datetime | None:
        raw = await read_json(self.path)
        if not raw:
            return None
        ts = raw.get("lastBeat")
        if ts:
            try:
                self._last = datetime.fromisoformat(ts)
            except ValueError:
                self._last = None
        return self._last

    @property
    def last(self) -> datetime | None:
        return self._last

    async def beat(self) -> None:
        now = datetime.now(timezone.utc)
        async with self._lock:
            self._last = now
            await write_json(self.path, {"lastBeat": now.isoformat()})

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ..logger import get_logger

log = get_logger(__name__)


async def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return await asyncio.to_thread(_read_sync, path)


async def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(_write_sync, path, data)


def _read_sync(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_sync(path: Path, data: Any) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class JSONFile:
    """Single-file JSON store with an asyncio.Lock for atomic write."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def load(self) -> Any:
        async with self._lock:
            return await read_json(self.path)

    async def save(self, data: Any) -> None:
        async with self._lock:
            await write_json(self.path, data)


def list_json_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix == ".json" and p.is_file())

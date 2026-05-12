from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path

from ..logger import get_logger
from ..models import User
from .json_store import list_json_files, read_json, write_json

log = get_logger(__name__)


class UserRepo:
    """In-memory user dict, keyed by Discord channel ID, write-through to JSON."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, User] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    @property
    def users_dir(self) -> Path:
        return self.root / "users"

    async def load_all(self) -> None:
        self.users_dir.mkdir(parents=True, exist_ok=True)
        for path in list_json_files(self.users_dir):
            try:
                raw = await read_json(path)
                if not raw:
                    continue
                user = User.from_dict(raw)
                key = self._key_of(user)
                if key:
                    self._cache[key] = user
            except Exception as exc:
                log.exception("Failed to load user %s: %s", path, exc)
        log.info("Loaded %d users from %s", len(self._cache), self.users_dir)

    @staticmethod
    def _key_of(user: User) -> str:
        return user.channel_id

    def _lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def _path_for(self, key: str) -> Path:
        return self.users_dir / f"{key}.json"

    def all(self) -> list[User]:
        return list(self._cache.values())

    def find(self, channel_id: str) -> User | None:
        return self._cache.get(channel_id)

    def find_by_account(self, account: str) -> User | None:
        for u in self._cache.values():
            if u.profile.account == account:
                return u
        return None

    def by_subscription_board(self, board: str) -> list[User]:
        board_l = board.lower()
        out = []
        for u in self._cache.values():
            if not u.enable:
                continue
            for s in u.subscribes:
                if s.board.lower() == board_l:
                    out.append(u)
                    break
        return out

    def iter_active(self) -> Iterable[User]:
        return (u for u in self._cache.values() if u.enable and u.channel_id)

    async def save(self, user: User) -> None:
        key = self._key_of(user)
        if not key:
            raise ValueError("User has no channel_id; cannot persist")
        user.touch()
        self._cache[key] = user
        async with self._lock_for(key):
            await write_json(self._path_for(key), user.to_dict())

    async def delete(self, channel_id: str) -> None:
        async with self._lock_for(channel_id):
            self._cache.pop(channel_id, None)
            path = self._path_for(channel_id)
            if path.exists():
                path.unlink()

    async def disable_for_guild(self, guild_id: str) -> int:
        """Mark all users bound to channels in a removed guild as disabled.

        Returns count of disabled users.
        """
        n = 0
        for u in list(self._cache.values()):
            if u.profile.discord and u.profile.discord.guild_id == guild_id and u.enable:
                u.enable = False
                await self.save(u)
                n += 1
        return n

    async def flush(self) -> None:
        """Re-persist all in-memory users (defensive on shutdown)."""
        for user in self._cache.values():
            try:
                await write_json(self._path_for(self._key_of(user)), user.to_dict())
            except Exception as exc:
                log.exception("Flush user failed: %s", exc)

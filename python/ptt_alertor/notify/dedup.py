from __future__ import annotations

import hashlib
import time

DEFAULT_TTL = 300  # 5 minutes, port from jobs/check.go msgCacheExpire


def _hash(account: str, channel_id: str, content: str) -> str:
    raw = f"{account}_{channel_id}_{content}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()


class Deduper:
    """In-memory dedup cache keyed by md5(account + channel_id + content).

    Replicates jobs/check.go isMessageSent: 5-minute TTL, per-message lazy expiry.
    Not persistent — restart clears it (acceptable: at worst one duplicate per restart).
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL) -> None:
        self.ttl = ttl_seconds
        self._cache: dict[str, float] = {}

    def is_duplicate(self, account: str, channel_id: str, content: str) -> bool:
        now = time.monotonic()
        key = _hash(account, channel_id, content)
        self._gc(now)
        if key in self._cache and self._cache[key] > now:
            return True
        self._cache[key] = now + self.ttl
        return False

    def _gc(self, now: float) -> None:
        if len(self._cache) < 1000:
            return
        expired = [k for k, exp in self._cache.items() if exp <= now]
        for k in expired:
            self._cache.pop(k, None)

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)

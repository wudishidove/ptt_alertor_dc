from __future__ import annotations

import asyncio
from datetime import datetime

from ..context import AppContext
from ..crawler import URLNotFound, fetch_articles
from ..logger import get_logger
from .dispatch import dispatch_keyword_author, dispatch_pushsum

log = get_logger(__name__)

RESYNC_INTERVAL = 30.0  # how often to re-detect boards added/removed


class KeywordChecker:
    """Polls each subscribed board's index page, dispatches new articles."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._tasks: dict[str, asyncio.Task] = {}
        self._stop: asyncio.Event | None = None

    async def run(self, stop: asyncio.Event) -> None:
        self._stop = stop
        log.info("KeywordChecker supervisor started")
        try:
            while not stop.is_set():
                self._sync_tasks()
                try:
                    await asyncio.wait_for(stop.wait(), timeout=RESYNC_INTERVAL)
                except asyncio.TimeoutError:
                    continue
                else:
                    break
        finally:
            await self._cancel_all()
            log.info("KeywordChecker supervisor stopped")

    def _sync_tasks(self) -> None:
        wanted = set(self.ctx.sub_index.boards()) | set(
            self.ctx.pushsum_subs.boards()
        )
        # spawn missing
        for board in wanted:
            if board not in self._tasks or self._tasks[board].done():
                self._tasks[board] = asyncio.create_task(
                    self._poll_board(board), name=f"kwchk:{board}"
                )
        # cancel removed
        for board in list(self._tasks.keys()):
            if board not in wanted:
                t = self._tasks.pop(board)
                t.cancel()

    async def _cancel_all(self) -> None:
        for t in self._tasks.values():
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def _poll_board(self, board: str) -> None:
        stop = self._stop
        assert stop is not None
        log.info("Polling board %s", board)
        backoff = 1.0
        while not stop.is_set():
            interval = self._interval_for(board)
            try:
                articles = await fetch_articles(self.ctx.crawler, board, -1)
                if articles:
                    new = await self.ctx.board_repo.update_after_fetch(board, articles)
                    if new:
                        log.info("Board %s: %d new articles", board, len(new))
                        for a in new:
                            await dispatch_keyword_author(self.ctx, a)
                            await dispatch_pushsum(self.ctx, a)
                backoff = 1.0
            except URLNotFound:
                log.warning("Board %s not found; backing off", board)
                interval = max(interval, 60.0)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.ctx.status.crawler_errors += 1
                log.warning("Board %s fetch failed: %s", board, exc)
                interval = min(60.0, interval * backoff)
                backoff = min(backoff * 2, 30.0)

            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
            else:
                break

    def _interval_for(self, board: str) -> float:
        s = self.ctx.settings
        if board.lower() in (b.lower() for b in s.high_boards):
            return s.poll_interval_high
        hour = datetime.now().astimezone().hour
        if 3 <= hour < 7:
            return s.poll_interval_offpeak
        return s.poll_interval_normal

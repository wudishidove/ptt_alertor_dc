from __future__ import annotations

import asyncio

from ..context import AppContext
from ..crawler import URLNotFound, fetch_articles
from ..logger import get_logger
from ..matching import hits_threshold
from ..models import Article
from ..notify import Notification

log = get_logger(__name__)

PAGES_TO_SCAN = 2  # latest + previous


class PushsumChecker:
    """Re-scans the latest pages of pushsum-subscribed boards.

    Catches articles whose push count grew enough to cross a threshold
    after they were first indexed by keyword_checker.
    """

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        # (code, channel_id, direction) -> already notified
        self._notified: dict[tuple[str, str, str], bool] = {}

    async def run(self, stop: asyncio.Event) -> None:
        # Treat value as seconds (consistent with other intervals); floor at
        # 30s — re-scanning every page below that is wasteful.
        interval = max(self.ctx.settings.pushsum_poll_interval, 30.0)
        log.info("PushsumChecker started (rescan every %.0fs)", interval)
        while not stop.is_set():
            try:
                await self._tick()
            except Exception as exc:
                log.exception("Pushsum tick failed: %s", exc)
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
            else:
                break
        log.info("PushsumChecker stopped")

    async def _tick(self) -> None:
        for board in self.ctx.pushsum_subs.boards():
            articles: list[Article] = []
            try:
                articles = await fetch_articles(self.ctx.crawler, board, -1)
            except URLNotFound:
                continue
            except Exception as exc:
                log.warning("Pushsum board %s fetch failed: %s", board, exc)
                continue
            await self._dispatch(board, articles)

    async def _dispatch(self, board: str, articles: list[Article]) -> None:
        for article in articles:
            if not article.code:
                continue
            for cid in self.ctx.pushsum_subs.subscribers(board):
                user = self.ctx.user_repo.find(cid)
                if user is None or not user.enable:
                    continue
                sub = user.find_subscription(board)
                if sub is None or sub.push_sum.is_empty():
                    continue
                up = sub.push_sum.up
                down = sub.push_sum.down
                if not hits_threshold(article.push_sum, up, down):
                    continue
                direction = "up" if article.push_sum >= up > 0 else "down"
                key = (article.code, cid, direction)
                if self._notified.get(key):
                    continue
                content = f"推噓文@{board}\n{article.format_with_pushsum()}"
                ok = await self.ctx.sender.send(
                    Notification(
                        account=user.profile.account,
                        channel_id=cid,
                        content=content,
                        sub_type="pushsum",
                    )
                )
                if ok:
                    self._notified[key] = True

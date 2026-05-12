from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ..context import AppContext
from ..crawler import URLNotFound, fetch_article
from ..logger import get_logger
from ..notify import Notification

log = get_logger(__name__)


class CommentChecker:
    """Polls each tracked article URL, notifies subscribers when new comments appear."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._last_seen: dict[str, datetime] = {}

    async def run(self, stop: asyncio.Event) -> None:
        interval = self.ctx.settings.comment_poll_interval
        log.info("CommentChecker started (interval=%.0fs)", interval)
        while not stop.is_set():
            try:
                await self._tick()
            except Exception as exc:
                log.exception("Comment tick failed: %s", exc)
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
            else:
                break
        log.info("CommentChecker stopped")

    async def _tick(self) -> None:
        codes = self.ctx.article_subs.codes()
        for code in codes:
            board = self.ctx.article_subs.board_of(code)
            if not board:
                continue
            try:
                art = await fetch_article(self.ctx.crawler, board, code)
            except URLNotFound:
                log.info("Article %s/%s gone, removing subscribers", board, code)
                await self._purge(board, code)
                continue
            except Exception as exc:
                log.warning("Comment fetch failed for %s: %s", code, exc)
                continue

            new_comments = self._diff_new(code, art.comments)
            if not new_comments:
                continue

            channels = self.ctx.article_subs.subscribers(code)
            for cid in channels:
                user = self.ctx.user_repo.find(cid)
                if user is None or not user.enable:
                    continue
                lines = [f"推文@{board}", art.title, art.link, ""]
                for c in new_comments:
                    when = c.datetime_.strftime("%m/%d %H:%M") if c.datetime_ else ""
                    lines.append(f"{c.tag} {c.user_id}: {c.content} ({when})")
                content = "\n".join(lines).rstrip()
                await self.ctx.sender.send(
                    Notification(
                        account=user.profile.account,
                        channel_id=cid,
                        content=content,
                        sub_type="comment",
                    )
                )
            if art.last_push_datetime:
                self._last_seen[code] = art.last_push_datetime

    def _diff_new(self, code: str, comments) -> list:
        if code not in self._last_seen:
            # First sighting: seed baseline to current latest, don't notify history.
            timestamps = [c.datetime_ for c in comments if c.datetime_]
            self._last_seen[code] = max(timestamps) if timestamps else datetime.min.replace(
                tzinfo=timezone.utc
            )
            return []
        last = self._last_seen[code]
        return [c for c in comments if c.datetime_ and c.datetime_ > last]

    async def _purge(self, board: str, code: str) -> None:
        # Remove from article_subs reverse index
        for cid in self.ctx.article_subs.subscribers(code):
            user = self.ctx.user_repo.find(cid)
            if user is not None:
                sub = user.find_subscription(board)
                if sub and code in sub.articles:
                    sub.articles = [a for a in sub.articles if a != code]
                    user.remove_empty_subscriptions()
                    await self.ctx.user_repo.save(user)
        await self.ctx.article_subs.remove_all(code)
        self._last_seen.pop(code, None)

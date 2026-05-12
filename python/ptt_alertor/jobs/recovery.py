from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from ..context import AppContext
from ..crawler import URLNotFound, current_page, fetch_articles
from ..logger import get_logger
from .dispatch import dispatch_keyword_author, dispatch_pushsum

log = get_logger(__name__)

MAX_PAGES_BACK = 20  # safety net to avoid infinite walks


async def recover_from_last_heartbeat(ctx: AppContext) -> None:
    """One-shot startup recovery: catch up on missed articles since last heartbeat.

    Stops walking when:
      - article id <= saved max id for that board, OR
      - we've walked MAX_PAGES_BACK pages, OR
      - heartbeat is older than recovery_max_days (then we just baseline, no notify).
    """
    last = await ctx.heartbeat.load()
    now = datetime.now(timezone.utc)
    max_age = timedelta(days=ctx.settings.recovery_max_days)

    if last is None:
        log.info("Recovery: no heartbeat found; skipping recovery, will baseline live")
        await _baseline_only(ctx)
        return
    age = now - last
    if age > max_age:
        log.info(
            "Recovery: last heartbeat %s ago > %d days; skipping recovery",
            age,
            ctx.settings.recovery_max_days,
        )
        await _baseline_only(ctx)
        return

    log.info("Recovery: catching up since heartbeat %s (%.1f hours ago)", last, age.total_seconds() / 3600)

    boards = sorted(set(ctx.sub_index.boards()) | set(ctx.pushsum_subs.boards()))
    for board in boards:
        try:
            await _recover_board(ctx, board)
        except Exception as exc:
            log.exception("Recovery for board %s failed: %s", board, exc)
    log.info("Recovery completed")


async def _baseline_only(ctx: AppContext) -> None:
    """Fetch latest page of every subscribed board to seed baseline (no dispatch)."""
    boards = sorted(set(ctx.sub_index.boards()) | set(ctx.pushsum_subs.boards()))
    for board in boards:
        try:
            arts = await fetch_articles(ctx.crawler, board, -1)
            await ctx.board_repo.update_after_fetch(board, arts)
        except Exception as exc:
            log.warning("Baseline fetch for %s failed: %s", board, exc)


async def _recover_board(ctx: AppContext, board: str) -> None:
    saved_max = ctx.board_repo.get_max_id(board)
    try:
        latest = await fetch_articles(ctx.crawler, board, -1)
    except URLNotFound:
        log.warning("Recovery: board %s not found", board)
        return

    if not latest:
        return

    online_max = max((a.id for a in latest if a.id), default=0)

    # If saved_max == 0 it's our first run, just baseline (don't backfill).
    if saved_max == 0:
        await ctx.board_repo.update_after_fetch(board, latest)
        return
    if online_max <= saved_max:
        await ctx.board_repo.update_after_fetch(board, latest)
        return

    # Walk back pages until we cover saved_max.
    collected: list = list(latest)
    seen_ids = {a.id for a in collected if a.id}
    cur_page = await _safe_current_page(ctx, board)
    pages_walked = 0
    while pages_walked < MAX_PAGES_BACK and cur_page > 1:
        prev_page = cur_page - 1
        try:
            page_arts = await fetch_articles(ctx.crawler, board, prev_page)
        except Exception as exc:
            log.warning("Recovery walk %s page %d failed: %s", board, prev_page, exc)
            break
        added_any = False
        for a in page_arts:
            if not a.id or a.id in seen_ids:
                continue
            collected.append(a)
            seen_ids.add(a.id)
            added_any = True
        cur_page = prev_page
        pages_walked += 1
        if not added_any:
            break
        if min(a.id for a in page_arts if a.id) <= saved_max:
            break

    new_articles = [a for a in collected if a.id and a.id > saved_max]
    log.info(
        "Recovery board %s: %d new since saved_max=%d",
        board,
        len(new_articles),
        saved_max,
    )

    # Dispatch in chronological order (oldest -> newest)
    for art in sorted(new_articles, key=lambda x: x.id):
        await dispatch_keyword_author(ctx, art)
        await dispatch_pushsum(ctx, art)

    # Now update baseline (max_id moves forward to online_max)
    await ctx.board_repo.update_after_fetch(board, latest)


async def _safe_current_page(ctx: AppContext, board: str) -> int:
    try:
        return await current_page(ctx.crawler, board)
    except Exception:
        return 0

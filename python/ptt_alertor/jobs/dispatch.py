from __future__ import annotations

from ..context import AppContext
from ..logger import get_logger
from ..matching import match_any_keyword, match_author
from ..models import Article
from ..notify import Notification

log = get_logger(__name__)


async def dispatch_keyword_author(ctx: AppContext, article: Article) -> None:
    """For a freshly seen article, find subscribers whose keywords/authors match."""
    board = article.board
    if not board:
        return

    candidates = ctx.sub_index.subscribers(board)
    if not candidates:
        return

    for channel_id in candidates:
        user = ctx.user_repo.find(channel_id)
        if user is None or not user.enable:
            continue
        sub = user.find_subscription(board)
        if sub is None:
            continue

        kw_hit = match_any_keyword(article.title, sub.keywords) if sub.keywords else None
        author_hit: str | None = None
        if sub.authors:
            for author in sub.authors:
                if match_author(article.author, author):
                    author_hit = author
                    break
        if not kw_hit and not author_hit:
            continue

        header_parts: list[str] = []
        if kw_hit:
            header_parts.append(f"關鍵字「{kw_hit}」")
        if author_hit:
            header_parts.append(f"作者「{author_hit}」")
        header = "／".join(header_parts) + f"@{board}"

        content = f"{header}\n{article.format_simple()}"
        await ctx.sender.send(
            Notification(
                account=user.profile.account,
                channel_id=channel_id,
                content=content,
                sub_type="keyword" if kw_hit else "author",
            )
        )


async def dispatch_pushsum(ctx: AppContext, article: Article) -> None:
    """Find pushsum subscribers whose threshold this article hits."""
    board = article.board
    if not board:
        return
    candidates = ctx.pushsum_subs.subscribers(board)
    if not candidates:
        return
    from ..matching import hits_threshold

    for channel_id in candidates:
        user = ctx.user_repo.find(channel_id)
        if user is None or not user.enable:
            continue
        sub = user.find_subscription(board)
        if sub is None or sub.push_sum.is_empty():
            continue
        if not hits_threshold(article.push_sum, sub.push_sum.up, sub.push_sum.down):
            continue
        header = f"推噓文@{board}"
        content = f"{header}\n{article.format_with_pushsum()}"
        await ctx.sender.send(
            Notification(
                account=user.profile.account,
                channel_id=channel_id,
                content=content,
                sub_type="pushsum",
            )
        )

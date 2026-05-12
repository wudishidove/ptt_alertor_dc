from __future__ import annotations

from ..context import AppContext
from ..logger import get_logger
from ..notify import Notification

log = get_logger(__name__)


async def broadcast(ctx: AppContext, content: str) -> int:
    """Send the same content to every active Discord-bound user.

    Returns count of channels successfully notified.
    """
    if not content:
        return 0

    targets: list[str] = []
    for u in ctx.user_repo.iter_active():
        if u.channel_id and u.channel_id not in targets:
            targets.append(u.channel_id)

    log.info("Broadcasting to %d channels", len(targets))
    sent = 0
    for cid in targets:
        ok = await ctx.sender.send(
            Notification(
                account="broadcast",
                channel_id=cid,
                content=content,
                sub_type="broadcast",
            )
        )
        if ok:
            sent += 1
    log.info("Broadcast finished: %d/%d channels", sent, len(targets))
    return sent

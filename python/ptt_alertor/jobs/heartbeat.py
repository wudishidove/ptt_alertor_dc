from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ..context import AppContext
from ..logger import get_logger

log = get_logger(__name__)

INTERVAL = 60.0


async def run_heartbeat(ctx: AppContext, stop: asyncio.Event) -> None:
    log.info("Heartbeat task started (interval=%.0fs)", INTERVAL)
    while not stop.is_set():
        try:
            await ctx.heartbeat.beat()
            ctx.status.last_heartbeat = datetime.now(timezone.utc)
        except Exception as exc:
            log.exception("Heartbeat write failed: %s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=INTERVAL)
        except asyncio.TimeoutError:
            continue
        else:
            break
    log.info("Heartbeat task stopped")

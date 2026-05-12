from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..logger import get_logger
from .dedup import Deduper
from .splitter import split_message

if TYPE_CHECKING:
    import discord

log = get_logger(__name__)


@dataclass
class Notification:
    account: str
    channel_id: str
    content: str
    sub_type: str = ""  # keyword / author / pushsum / comment / broadcast


class DiscordSender:
    """Pushes notifications via the connected discord.py client.

    Drops duplicates within a 5-minute window (per Deduper), splits messages
    into <= 2000-char chunks, and logs send failures without crashing callers.
    """

    def __init__(self, deduper: Deduper) -> None:
        self.deduper = deduper
        self._bot: "discord.Client | None" = None

    def attach_bot(self, bot: "discord.Client") -> None:
        self._bot = bot

    @property
    def ready(self) -> bool:
        return self._bot is not None and self._bot.is_ready()

    async def send(self, n: Notification) -> bool:
        if not n.channel_id or not n.content:
            return False
        if self.deduper.is_duplicate(n.account, n.channel_id, n.content):
            return False
        if self._bot is None:
            log.warning("DiscordSender bot not attached, dropping message for %s", n.channel_id)
            return False

        channel = self._bot.get_channel(int(n.channel_id))
        if channel is None:
            try:
                channel = await self._bot.fetch_channel(int(n.channel_id))
            except Exception as exc:  # discord.NotFound etc
                log.warning(
                    "Channel %s not accessible (%s); skipping", n.channel_id, exc
                )
                return False

        sent_any = False
        for chunk in split_message(n.content):
            try:
                await channel.send(chunk)
                sent_any = True
            except Exception as exc:
                log.warning("Send to %s failed: %s", n.channel_id, exc)
                break
        if sent_any:
            log.info(
                "Sent: account=%s channel=%s subType=%s len=%d",
                n.account,
                n.channel_id,
                n.sub_type,
                len(n.content),
            )
        return sent_any

    async def fan_out(self, channel_ids: list[str], content: str, *, account_label: str = "broadcast", sub_type: str = "broadcast") -> int:
        """Send the same content to many channels concurrently.

        Returns count of successful deliveries.
        """
        if not channel_ids:
            return 0
        results = await asyncio.gather(
            *(
                self.send(
                    Notification(
                        account=account_label,
                        channel_id=cid,
                        content=content,
                        sub_type=sub_type,
                    )
                )
                for cid in channel_ids
            ),
            return_exceptions=True,
        )
        return sum(1 for r in results if r is True)

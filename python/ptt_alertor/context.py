from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .crawler import PTTClient
from .notify import Deduper, DiscordSender
from .settings import Settings
from .storage import (
    ArticleSubsRepo,
    BoardRepo,
    HeartbeatStore,
    PushsumSubsRepo,
    SubscriptionIndex,
    UserRepo,
)

if TYPE_CHECKING:
    from .bot.client import PTTAlertorBot


@dataclass
class BotStatus:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat: datetime | None = None
    discord_ready: bool = False
    crawler_errors: int = 0


@dataclass
class AppContext:
    settings: Settings
    user_repo: UserRepo
    board_repo: BoardRepo
    article_subs: ArticleSubsRepo
    pushsum_subs: PushsumSubsRepo
    heartbeat: HeartbeatStore
    sub_index: SubscriptionIndex
    deduper: Deduper
    sender: DiscordSender
    crawler: PTTClient
    status: BotStatus = field(default_factory=BotStatus)
    bot: "PTTAlertorBot | None" = None

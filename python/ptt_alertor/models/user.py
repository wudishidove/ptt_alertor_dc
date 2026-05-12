from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .subscription import Subscription


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DiscordIdentity:
    user_id: str = ""
    channel_id: str = ""
    channel_type: str = ""
    guild_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "userId": self.user_id,
            "channelId": self.channel_id,
            "channelType": self.channel_type,
            "guildId": self.guild_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DiscordIdentity | None:
        if not data:
            return None
        return cls(
            user_id=data.get("userId", ""),
            channel_id=data.get("channelId", ""),
            channel_type=data.get("channelType", ""),
            guild_id=data.get("guildId", ""),
        )


@dataclass
class Profile:
    account: str = ""
    discord: DiscordIdentity | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"account": self.account}
        if self.discord:
            out["discord"] = self.discord.to_dict()
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Profile:
        return cls(
            account=data.get("account", ""),
            discord=DiscordIdentity.from_dict(data.get("discord")),
        )


@dataclass
class User:
    enable: bool = True
    create_time: datetime = field(default_factory=_utcnow)
    update_time: datetime = field(default_factory=_utcnow)
    profile: Profile = field(default_factory=Profile)
    subscribes: list[Subscription] = field(default_factory=list)

    @property
    def account(self) -> str:
        return self.profile.account

    @property
    def channel_id(self) -> str:
        return self.profile.discord.channel_id if self.profile.discord else ""

    def find_subscription(self, board: str) -> Subscription | None:
        board_lower = board.lower()
        for s in self.subscribes:
            if s.board.lower() == board_lower:
                return s
        return None

    def get_or_create_subscription(self, board: str) -> Subscription:
        sub = self.find_subscription(board)
        if sub is None:
            sub = Subscription(board=board)
            self.subscribes.append(sub)
        return sub

    def remove_empty_subscriptions(self) -> None:
        self.subscribes = [s for s in self.subscribes if not s.is_empty()]

    def touch(self) -> None:
        self.update_time = _utcnow()

    def to_dict(self) -> dict[str, Any]:
        return {
            "enable": self.enable,
            "createTime": self.create_time.isoformat(),
            "updateTime": self.update_time.isoformat(),
            "Profile": self.profile.to_dict(),
            "Subscribes": [s.to_dict() for s in self.subscribes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> User:
        ct = data.get("createTime")
        ut = data.get("updateTime")
        return cls(
            enable=bool(data.get("enable", True)),
            create_time=datetime.fromisoformat(ct) if ct else _utcnow(),
            update_time=datetime.fromisoformat(ut) if ut else _utcnow(),
            profile=Profile.from_dict(data.get("Profile") or data.get("profile") or {}),
            subscribes=[
                Subscription.from_dict(s)
                for s in (data.get("Subscribes") or data.get("subscribes") or [])
            ],
        )

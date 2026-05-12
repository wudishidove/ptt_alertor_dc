import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ptt_alertor.models import (
    DiscordIdentity,
    Profile,
    PushSum,
    Subscription,
    User,
)
from ptt_alertor.storage import (
    ArticleSubsRepo,
    BoardRepo,
    HeartbeatStore,
    PushsumSubsRepo,
    SubscriptionIndex,
    UserRepo,
)
from ptt_alertor.models.board import BoardSnapshot
from ptt_alertor.models.article import Article


def _make_user(channel_id: str) -> User:
    return User(
        profile=Profile(
            account=f"discord-{channel_id}",
            discord=DiscordIdentity(
                user_id="100",
                channel_id=channel_id,
                channel_type="guild_text",
                guild_id="200",
            ),
        ),
        subscribes=[
            Subscription(
                board="EZsoft",
                keywords=["python", "rust"],
                authors=["obov"],
                push_sum=PushSum(up=50, down=-30),
            )
        ],
    )


@pytest.mark.asyncio
async def test_user_repo_save_and_reload(tmp_path: Path):
    repo = UserRepo(tmp_path)
    await repo.load_all()
    await repo.save(_make_user("999"))
    assert repo.find("999") is not None
    assert (tmp_path / "users" / "999.json").exists()

    repo2 = UserRepo(tmp_path)
    await repo2.load_all()
    user = repo2.find("999")
    assert user is not None
    assert user.profile.account == "discord-999"
    assert user.subscribes[0].keywords == ["python", "rust"]
    assert user.subscribes[0].push_sum.up == 50


@pytest.mark.asyncio
async def test_subscription_index_rebuild(tmp_path: Path):
    repo = UserRepo(tmp_path)
    await repo.load_all()
    await repo.save(_make_user("c1"))
    await repo.save(_make_user("c2"))
    idx = SubscriptionIndex(repo)
    idx.rebuild()
    assert idx.subscribers("EZsoft") == {"c1", "c2"}
    assert idx.subscribers("Unknown") == set()


@pytest.mark.asyncio
async def test_board_repo_diff(tmp_path: Path):
    repo = BoardRepo(tmp_path)
    await repo.load_all()
    arts1 = [Article(id=100, code="M.100.A", title="t1"), Article(id=101, code="M.101.A", title="t2")]
    new = await repo.update_after_fetch("EZsoft", arts1)
    assert {a.id for a in new} == {100, 101}

    arts2 = [
        Article(id=101, code="M.101.A", title="t2"),
        Article(id=102, code="M.102.A", title="t3"),
    ]
    new2 = await repo.update_after_fetch("EZsoft", arts2)
    assert {a.id for a in new2} == {102}


@pytest.mark.asyncio
async def test_article_subs(tmp_path: Path):
    repo = ArticleSubsRepo(tmp_path)
    await repo.load()
    await repo.add("M.999.A.X", "EZsoft", "channel-1")
    await repo.add("M.999.A.X", "EZsoft", "channel-2")
    assert repo.subscribers("M.999.A.X") == {"channel-1", "channel-2"}

    await repo.remove("M.999.A.X", "channel-1")
    assert repo.subscribers("M.999.A.X") == {"channel-2"}

    await repo.remove("M.999.A.X", "channel-2")
    assert repo.subscribers("M.999.A.X") == set()
    assert "M.999.A.X" not in repo.codes()


@pytest.mark.asyncio
async def test_pushsum_subs(tmp_path: Path):
    repo = PushsumSubsRepo(tmp_path)
    await repo.load()
    await repo.add("Gossiping", "c1")
    await repo.add("Gossiping", "c2")
    assert repo.subscribers("Gossiping") == {"c1", "c2"}
    await repo.remove("Gossiping", "c1")
    assert repo.subscribers("Gossiping") == {"c2"}


@pytest.mark.asyncio
async def test_heartbeat(tmp_path: Path):
    hb = HeartbeatStore(tmp_path)
    assert await hb.load() is None
    await hb.beat()
    assert hb.last is not None
    hb2 = HeartbeatStore(tmp_path)
    last = await hb2.load()
    assert last is not None
    assert (datetime.now(timezone.utc) - last).total_seconds() < 10

from __future__ import annotations

import json
from datetime import datetime, timezone

import aiohttp_jinja2
from aiohttp import web

from ..context import AppContext
from ..jobs import broadcast as broadcast_job
from ..logger import get_logger
from ..models import Profile, PushSum, Subscription, User

log = get_logger(__name__)


def _ctx(request: web.Request) -> AppContext:
    return request.app["ctx"]


# ----- public-ish -----

@aiohttp_jinja2.template("index.html")
async def index(request: web.Request) -> dict:
    ctx = _ctx(request)
    now = datetime.now(timezone.utc)
    uptime = (now - ctx.status.started_at).total_seconds()
    return {
        "status": ctx.status,
        "settings": ctx.settings,
        "uptime_seconds": int(uptime),
        "user_count": len(ctx.user_repo.all()),
        "board_count": len(set(ctx.sub_index.boards()) | set(ctx.pushsum_subs.boards())),
        "article_track_count": len(ctx.article_subs.codes()),
    }


async def boards(request: web.Request) -> web.Response:
    ctx = _ctx(request)
    out = []
    boards = sorted(set(ctx.sub_index.boards()) | set(ctx.pushsum_subs.boards()))
    for board in boards:
        kw_subs = ctx.sub_index.subscribers(board)
        ps_subs = ctx.pushsum_subs.subscribers(board)
        out.append(
            {
                "board": board,
                "keywordSubscribers": len(kw_subs),
                "pushsumSubscribers": len(ps_subs),
            }
        )
    return web.json_response(out)


# ----- admin (Basic Auth) -----

@aiohttp_jinja2.template("users.html")
async def users_index(request: web.Request) -> dict:
    ctx = _ctx(request)
    users = ctx.user_repo.all()
    stats = {
        "total": len(users),
        "enabled": sum(1 for u in users if u.enable),
        "disabled": sum(1 for u in users if not u.enable),
        "idle": sum(1 for u in users if not u.subscribes),
        "boards": 0,
        "keywords": 0,
        "authors": 0,
        "articles": 0,
        "pushsum": 0,
    }
    for u in users:
        for s in u.subscribes:
            stats["boards"] += 1
            stats["keywords"] += len(s.keywords)
            stats["authors"] += len(s.authors)
            stats["articles"] += len(s.articles)
            if not s.push_sum.is_empty():
                stats["pushsum"] += 1
    users_sorted = sorted(users, key=lambda u: u.update_time, reverse=True)
    return {"users": users_sorted, "stats": stats}


async def user_find(request: web.Request) -> web.Response:
    ctx = _ctx(request)
    account = request.match_info["account"]
    user = ctx.user_repo.find_by_account(account) or ctx.user_repo.find(account)
    if user is None:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response(user.to_dict())


async def user_create(request: web.Request) -> web.Response:
    ctx = _ctx(request)
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid json"}, status=400)

    user = _user_from_payload(data)
    if user.channel_id == "":
        return web.json_response({"error": "discord.channelId required"}, status=400)
    await ctx.user_repo.save(user)
    ctx.sub_index.update_for_user(user)
    return web.json_response(user.to_dict(), status=201)


async def user_modify(request: web.Request) -> web.Response:
    ctx = _ctx(request)
    account = request.match_info["account"]
    existing = ctx.user_repo.find_by_account(account) or ctx.user_repo.find(account)
    if existing is None:
        return web.json_response({"error": "not found"}, status=404)
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid json"}, status=400)

    if "enable" in data:
        existing.enable = bool(data["enable"])
    if "Subscribes" in data or "subscribes" in data:
        subs_raw = data.get("Subscribes") or data.get("subscribes") or []
        existing.subscribes = [Subscription.from_dict(s) for s in subs_raw]
    await ctx.user_repo.save(existing)
    ctx.sub_index.update_for_user(existing)
    # Update pushsum reverse index too
    await _resync_pushsum_for_user(ctx, existing)
    return web.json_response(existing.to_dict())


async def broadcast_handler(request: web.Request) -> web.Response:
    ctx = _ctx(request)
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid json"}, status=400)
    content = (data.get("content") or "").strip()
    if not content:
        return web.json_response({"error": "content is required"}, status=400)
    sent = await broadcast_job(ctx, content)
    return web.json_response({"sent": sent})


# ----- helpers -----

def _user_from_payload(data: dict) -> User:
    user = User.from_dict(data)
    if not user.profile.account and user.channel_id:
        user.profile.account = f"discord-{user.channel_id}"
    return user


async def _resync_pushsum_for_user(ctx: AppContext, user: User) -> None:
    cid = user.channel_id
    if not cid:
        return
    # Remove from all existing pushsum boards
    for board in list(ctx.pushsum_subs.boards()):
        if cid in ctx.pushsum_subs.subscribers(board):
            await ctx.pushsum_subs.remove(board, cid)
    # Re-add for non-empty pushsum subscriptions
    for s in user.subscribes:
        if not s.push_sum.is_empty():
            await ctx.pushsum_subs.add(s.board, cid)

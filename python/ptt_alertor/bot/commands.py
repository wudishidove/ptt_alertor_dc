from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timezone

from ..crawler import URLNotFound, article_exists, fetch_article
from ..logger import get_logger
from ..matching.keyword import REGEXP_PREFIX
from ..models import DiscordIdentity, Profile, PushSum, Subscription, User
from ..context import AppContext

log = get_logger(__name__)

ARTICLE_LIMIT = 50
UPDATE_FAILED_MSG = "失敗，請稍後重試。"

_KEYWORD_RE = re.compile(
    r"^(新增|刪除)\s+([^,，][\w\-_,，\.]*[^,，:\s])\s*:?\s+(\*|.*[^\s])$"
)
_AUTHOR_RE = re.compile(
    r"^(新增作者|刪除作者)\s+([^,，][\w\-_,，\.]*[^,，:\s])\s*:?\s+(\*|[\s,\w]+)$"
)
_PUSHSUM_RE = re.compile(
    r"^(新增推文數|新增噓文數)\s+([^,，][\w\-_,，\.]*[^,，:\s])\s*:?\s+(100|[1-9][0-9]|[0-9])$"
)
_ARTICLE_URL_RE = re.compile(
    r"^(新增推文|刪除推文)\s+https?://www\.ptt\.cc/bbs/([\w\-_]+)/(M\.\d+\.A\.\w+)\.html$"
)

ERROR_TIPS = [
    "指令格式錯誤。",
    "1. 需以空白分隔動作、板名、參數。",
    "2. 板名欄位開頭與結尾不可有逗號。",
    "3. 板名欄位間不允許空白字元。",
]

COMMANDS_TEXT = (
    "[一般]\n"
    "指令：可使用的指令清單\n"
    "清單：設定的看板、關鍵字、作者、文章\n"
    "notify：將通知綁定到目前頻道\n\n"
    "[關鍵字相關]\n"
    "新增 看板 關鍵字：新增追蹤關鍵字（支援 kw1&kw2、regexp:、!排除）\n"
    "刪除 看板 關鍵字|*：取消追蹤關鍵字\n"
    "範例：新增 gossiping,movie 金城武,結衣\n\n"
    "[作者相關]\n"
    "新增作者 看板 作者：新增追蹤作者\n"
    "刪除作者 看板 作者|*：取消追蹤作者\n"
    "範例：新增作者 gossiping ffaarr,obov\n\n"
    "[推噓文數相關]\n"
    "新增(推/噓)文數 看板 數值：通知推或噓文數（0-100，0 = 取消）\n"
    "範例：新增推文數 joke,beauty 50\n\n"
    "[推文追蹤]\n"
    "新增推文 網址：追蹤特定文章新留言\n"
    "刪除推文 網址：取消文章追蹤\n"
    "範例：新增推文 https://www.ptt.cc/bbs/EZsoft/M.1497363598.A.74E.html"
)


def discord_account_key(channel_id: str) -> str:
    return f"discord-{channel_id}"


def split_param_string(raw: str) -> list[str]:
    raw = raw.strip().strip(",，")
    parts = re.split(r"[,，]", raw)
    return [p.strip() for p in parts if p.strip()]


async def save_user_channel(
    ctx: AppContext,
    user_id: str,
    channel_id: str,
    channel_type: str,
    guild_id: str,
) -> User:
    user = ctx.user_repo.find(channel_id)
    if user is None:
        user = User(
            profile=Profile(
                account=discord_account_key(channel_id),
                discord=DiscordIdentity(
                    user_id=user_id,
                    channel_id=channel_id,
                    channel_type=channel_type,
                    guild_id=guild_id,
                ),
            ),
        )
    else:
        user.enable = True
        user.profile.account = discord_account_key(channel_id)
        user.profile.discord = DiscordIdentity(
            user_id=user_id,
            channel_id=channel_id,
            channel_type=channel_type,
            guild_id=guild_id,
        )
    await ctx.user_repo.save(user)
    ctx.sub_index.update_for_user(user)
    return user


async def handle_command(ctx: AppContext, text: str, channel_id: str) -> str:
    """Top-level dispatch. Returns the reply text (empty string = silent)."""
    text = text.strip()
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    head = parts[0].lower()

    if head in ("debug",):
        return _handle_debug(ctx, channel_id)
    if head in ("清單", "list"):
        return _handle_list(ctx, channel_id)
    if head in ("指令", "help"):
        return COMMANDS_TEXT
    if head in ("新增", "刪除"):
        return await _handle_keyword_or_delete(ctx, text, head, channel_id)
    if head in ("新增作者", "刪除作者"):
        return await _handle_author(ctx, text, head, channel_id)
    if head in ("新增推文數", "新增噓文數"):
        return await _handle_pushsum(ctx, text, head, channel_id)
    if head in ("新增推文", "刪除推文"):
        return await _handle_article(ctx, text, head, channel_id)

    return "無此指令，請打「指令」查看指令清單"


def _handle_debug(ctx: AppContext, channel_id: str) -> str:
    user = ctx.user_repo.find(channel_id)
    if not user:
        return "尚未綁定，請輸入 notify"
    return (
        f"channel_id={channel_id} account={user.profile.account} "
        f"enable={user.enable} subs={len(user.subscribes)}"
    )


def _handle_list(ctx: AppContext, channel_id: str) -> str:
    user = ctx.user_repo.find(channel_id)
    if not user or not user.subscribes:
        return "尚未建立清單。請打「指令」查看新增方法。"
    parts = []
    for s in user.subscribes:
        if s.is_empty():
            continue
        parts.append(f"[{s.board}]")
        if s.keywords:
            parts.append("關鍵字：" + ", ".join(s.keywords))
        if s.authors:
            parts.append("作者：" + ", ".join(s.authors))
        if s.push_sum.up:
            parts.append(f"推文數 ≥ {s.push_sum.up}")
        if s.push_sum.down:
            parts.append(f"噓文數 ≤ {s.push_sum.down}")
        if s.articles:
            parts.append("追蹤推文：" + ", ".join(s.articles))
        parts.append("")
    return "\n".join(parts).strip() or "尚未建立清單。請打「指令」查看新增方法。"


def _ensure_user(ctx: AppContext, channel_id: str) -> User | None:
    return ctx.user_repo.find(channel_id)


def _format_error(head: str, lines: Iterable[str]) -> str:
    return "\n".join([*ERROR_TIPS, *lines, "正確範例：", f"{head} gossiping,joke 金城武,結衣"])


async def _handle_keyword_or_delete(ctx: AppContext, text: str, head: str, channel_id: str) -> str:
    m = _KEYWORD_RE.match(text)
    if not m:
        return _format_error(head, [])

    user = _ensure_user(ctx, channel_id)
    if user is None:
        return "尚未綁定，請先輸入 notify"

    boards = split_param_string(m.group(2))
    payload = m.group(3)
    keywords = (
        [payload] if payload.startswith(REGEXP_PREFIX) else split_param_string(payload)
    )
    if payload.startswith(REGEXP_PREFIX) and not _is_valid_regex(payload):
        return "正規表示式錯誤，請檢查規則。"

    for board in boards:
        sub = user.get_or_create_subscription(board)
        if head == "新增":
            for kw in keywords:
                if kw not in sub.keywords:
                    sub.keywords.append(kw)
        else:
            if keywords == ["*"]:
                sub.keywords.clear()
            else:
                sub.keywords = [k for k in sub.keywords if k not in keywords]
    user.remove_empty_subscriptions()
    await ctx.user_repo.save(user)
    ctx.sub_index.update_for_user(user)
    return f"{head}成功"


async def _handle_author(ctx: AppContext, text: str, head: str, channel_id: str) -> str:
    m = _AUTHOR_RE.match(text)
    if not m:
        return _format_error(head, ["4. 作者為半形英文與數字組成。"])

    user = _ensure_user(ctx, channel_id)
    if user is None:
        return "尚未綁定，請先輸入 notify"

    boards = split_param_string(m.group(2))
    authors = split_param_string(m.group(3))

    for board in boards:
        sub = user.get_or_create_subscription(board)
        if head == "新增作者":
            for a in authors:
                if a not in sub.authors:
                    sub.authors.append(a)
        else:
            if authors == ["*"]:
                sub.authors.clear()
            else:
                sub.authors = [a for a in sub.authors if a not in authors]
    user.remove_empty_subscriptions()
    await ctx.user_repo.save(user)
    ctx.sub_index.update_for_user(user)
    return f"{head}成功"


async def _handle_pushsum(ctx: AppContext, text: str, head: str, channel_id: str) -> str:
    m = _PUSHSUM_RE.match(text)
    if not m:
        return _format_error(head, ["4. 推噓文數需為介於 0-100 的數字"])

    user = _ensure_user(ctx, channel_id)
    if user is None:
        return "尚未綁定，請先輸入 notify"

    boards = split_param_string(m.group(2))
    n = int(m.group(3))

    for board in boards:
        if board.lower() == "allpost":
            return "推文數通知不支援 ALLPOST 板。"
        sub = user.get_or_create_subscription(board)
        if head == "新增推文數":
            sub.push_sum.up = n
        else:
            sub.push_sum.down = -n
        if sub.push_sum.is_empty():
            await ctx.pushsum_subs.remove(board, channel_id)
        else:
            await ctx.pushsum_subs.add(board, channel_id)
    user.remove_empty_subscriptions()
    await ctx.user_repo.save(user)
    return f"{head}成功"


async def _handle_article(ctx: AppContext, text: str, head: str, channel_id: str) -> str:
    m = _ARTICLE_URL_RE.match(text)
    if not m:
        return (
            "指令格式錯誤。\n"
            "1. 網址與指令需至少一個空白。\n"
            "2. 網址錯誤格式。\n"
            "正確範例：\n"
            f"{head} https://www.ptt.cc/bbs/EZsoft/M.1497363598.A.74E.html"
        )

    user = _ensure_user(ctx, channel_id)
    if user is None:
        return "尚未綁定，請先輸入 notify"

    board = m.group(2)
    code = m.group(3)

    if head == "新增推文":
        # Validate article exists
        try:
            ok = await article_exists(ctx.crawler, board, code)
        except Exception as exc:
            log.warning("Comment add: exists check failed: %s", exc)
            ok = False
        if not ok:
            return "文章不存在"
        if _count_articles(user) >= ARTICLE_LIMIT:
            return f"推文追蹤最多 {ARTICLE_LIMIT} 篇。"

        # Initialize article comment baseline so checker can diff
        try:
            art = await fetch_article(ctx.crawler, board, code)
        except URLNotFound:
            return "文章不存在"
        sub = user.get_or_create_subscription(board)
        if code not in sub.articles:
            sub.articles.append(code)
        await ctx.article_subs.add(code, board, channel_id)

        # Save baseline article so comment_checker can compare lastPushDateTime
        snap = ctx.board_repo.get(board)
        if snap is None:
            from ..models.board import BoardSnapshot
            snap = BoardSnapshot(board=board)
        # Attach single-article baseline using its last push datetime; persisted via board snapshot is heavy,
        # so we keep it implicit — comment_checker will fetch and store its own state in user subs.
        _ = art  # silence unused

        await ctx.user_repo.save(user)
        return "新增推文成功"

    # 刪除推文
    sub = user.find_subscription(board)
    if sub is None or code not in sub.articles:
        return "未追蹤該推文"
    sub.articles = [a for a in sub.articles if a != code]
    await ctx.article_subs.remove(code, channel_id)
    user.remove_empty_subscriptions()
    await ctx.user_repo.save(user)
    return "刪除推文成功"


def _count_articles(user: User) -> int:
    return sum(len(s.articles) for s in user.subscribes)


def _is_valid_regex(expr: str) -> bool:
    pattern = expr[len(REGEXP_PREFIX):]
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False

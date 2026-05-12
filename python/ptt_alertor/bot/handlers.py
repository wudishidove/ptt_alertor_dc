from __future__ import annotations

import re
from typing import TYPE_CHECKING

import discord

from ..context import AppContext
from ..logger import get_logger
from ..notify import split_message
from .commands import handle_command, save_user_channel

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

WELCOME_TEXT = (
    "歡迎使用 PTT Alertor。\n"
    "請輸入「notify」來設定 {target} 接收 PTT 最新文章通知。\n"
    "在伺服器頻道使用時請 @ 機器人，例如：@PttAlertor 指令\n"
    "私訊則直接輸入指令即可。"
)

# Matches <@123>, <@!123>, <@&123> (role mention shouldn't appear but harmless)
_MENTION_RE = re.compile(r"<@[!&]?(\d+)>")


def _channel_label(channel: discord.abc.MessageableChannel) -> str:
    if isinstance(channel, discord.DMChannel):
        return "私人訊息"
    return "此頻道"


def _channel_type_for(channel: discord.abc.MessageableChannel) -> str:
    if isinstance(channel, discord.DMChannel):
        return "dm"
    if isinstance(channel, discord.Thread):
        return "thread"
    return "guild_text"


def _guild_id_for(channel: discord.abc.MessageableChannel) -> str:
    guild = getattr(channel, "guild", None)
    return str(guild.id) if guild else ""


async def _send_safely(channel: discord.abc.MessageableChannel, text: str) -> None:
    if not text:
        return
    for chunk in split_message(text):
        try:
            await channel.send(chunk)
        except discord.DiscordException as exc:
            log.warning("Reply send failed: %s", exc)
            return


async def on_ready(ctx: AppContext) -> None:
    bot = ctx.bot
    if bot is None:
        return
    ctx.status.discord_ready = True
    log.info("Discord ready as %s (id=%s)", bot.user, getattr(bot.user, "id", "?"))
    try:
        await bot.change_presence(activity=discord.Game(name="監控 PTT 中..."))
    except Exception as exc:
        log.warning("change_presence failed: %s", exc)


async def on_message(ctx: AppContext, message: discord.Message) -> None:
    bot = ctx.bot
    if bot is None or message.author == bot.user or message.author.bot:
        return

    channel = message.channel
    is_dm = isinstance(channel, discord.DMChannel)
    raw_content = message.content or ""

    # In guild channels, we only process messages where the bot is @mentioned.
    # (Without MESSAGE_CONTENT intent, non-mention messages arrive with empty
    # content anyway — but the explicit check avoids treating ambiguous events
    # as commands.)
    if not is_dm:
        bot_user = bot.user
        if bot_user is None or bot_user not in message.mentions:
            return

    text = _strip_self_mention(raw_content, bot.user.id if bot.user else 0).strip()
    if not text:
        if not is_dm:
            await _send_safely(
                channel,
                WELCOME_TEXT.format(target=_channel_label(channel)),
            )
        return

    channel_id = str(channel.id)
    head = text.split(maxsplit=1)[0].lower()

    if head == "notify":
        user = await save_user_channel(
            ctx,
            user_id=str(message.author.id),
            channel_id=channel_id,
            channel_type=_channel_type_for(channel),
            guild_id=_guild_id_for(channel),
        )
        await _send_safely(channel, f"已綁定通知頻道（account={user.profile.account}）。輸入「指令」查看可用指令。")
        return

    user = ctx.user_repo.find(channel_id)
    if user is None:
        await _send_safely(channel, WELCOME_TEXT.format(target=_channel_label(channel)))
        return

    reply = await handle_command(ctx, text, channel_id)
    await _send_safely(channel, reply)


def _strip_self_mention(content: str, bot_user_id: int) -> str:
    """Remove leading/trailing @bot mentions from message content."""
    if not bot_user_id:
        return content
    # Remove the bot's own mention tokens anywhere they appear
    def _is_self(m: re.Match) -> bool:
        return m.group(1) == str(bot_user_id)
    return _MENTION_RE.sub(lambda m: "" if _is_self(m) else m.group(0), content)


async def on_guild_join(ctx: AppContext, guild: discord.Guild) -> None:
    log.info("Joined guild: %s (id=%s)", guild.name, guild.id)


async def on_guild_remove(ctx: AppContext, guild: discord.Guild) -> None:
    """When kicked from a guild, disable all users bound to that guild's channels."""
    n = await ctx.user_repo.disable_for_guild(str(guild.id))
    log.info("Removed from guild %s; disabled %d users", guild.id, n)

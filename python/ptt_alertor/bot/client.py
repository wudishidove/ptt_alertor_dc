from __future__ import annotations

import discord

from ..context import AppContext
from . import handlers


def build_intents() -> discord.Intents:
    """Non-privileged intents only, matching the original Go (discordgo) bot.

    Without MESSAGE_CONTENT, ``message.content`` is populated only for:
      1. DMs to the bot
      2. Messages where the bot is @mentioned
      3. The bot's own messages
    Guild usage is expected to be "@mention me", DM usage is unrestricted.
    """
    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True
    intents.dm_messages = True
    return intents


class PTTAlertorBot(discord.Client):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(intents=build_intents())
        self.ctx = ctx
        ctx.bot = self
        ctx.sender.attach_bot(self)

    async def on_ready(self) -> None:
        await handlers.on_ready(self.ctx)

    async def on_message(self, message: discord.Message) -> None:
        await handlers.on_message(self.ctx, message)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await handlers.on_guild_join(self.ctx, guild)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await handlers.on_guild_remove(self.ctx, guild)

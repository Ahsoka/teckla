from discord_slash import SlashCommand
from discord.ext.commands import Bot

import discord

bot = Bot(command_prefix='/', intents=discord.Intents(messages=True, guilds=True))
slash = SlashCommand(bot)

from .commands import CommandsCog

bot.add_cog(CommandsCog(bot))

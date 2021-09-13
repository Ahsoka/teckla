from discord_slash.utils.manage_commands import create_option
from discord_slash import SlashCommand, SlashContext
from discord.ext.commands import Bot
from dotenv import load_dotenv

import os
import discord

load_dotenv()

bot = Bot(command_prefix='test.', intents=discord.Intents(messages=True, guilds=True))
slash = SlashCommand(bot, sync_commands=True)

@bot.event
async def on_ready():
    print(f"{bot.user} is ready to roll.")

bot.run(os.environ['testing-token'])

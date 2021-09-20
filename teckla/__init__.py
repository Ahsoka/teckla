from discord_slash import SlashCommand
from discord.ext.commands import Bot
from aiogoogle import Aiogoogle

import json
import discord

bot = Bot(command_prefix='/', intents=discord.Intents(messages=True, guilds=True))
slash = SlashCommand(bot)

with open('credentials.json') as file:
    client_creds = json.load(file)['web']
    client_creds['scopes'] = ['https://www.googleapis.com/auth/drive']
    client_creds['redirect_uri'] = client_creds['redirect_uris'][0]
    aio_google = Aiogoogle(client_creds=client_creds)

from .commands import CommandsCog

bot.add_cog(CommandsCog(bot))

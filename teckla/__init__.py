from sqlalchemy.ext.asyncio import create_async_engine
from discord_slash import SlashCommand
from discord.ext.commands import Bot
from aiogoogle import Aiogoogle

import json
import discord
import argparse

parser = argparse.ArgumentParser(description='Use this to set bot settings.')
parser.add_argument('-nt', '--not-testing', action='store_false', dest='testing')

config = parser.parse_args()

engine = create_async_engine('sqlite+aiosqlite:///test.db')

bot = Bot(command_prefix='/', intents=discord.Intents(messages=True, guilds=True))
# slash = SlashCommand(bot, sync_commands=True)
slash = SlashCommand(bot)

with open('credentials.json') as file:
    client_creds = json.load(file)['web']
    client_creds['scopes'] = ['https://www.googleapis.com/auth/documents']
    client_creds['redirect_uri'] = client_creds['redirect_uris'][0]
    aio_google = Aiogoogle(client_creds=client_creds)

from .commands import CommandsCog

bot.add_cog(CommandsCog(bot))

from sqlalchemy.ext.asyncio import create_async_engine
from discord_slash import SlashCommand
from discord.ext.commands import Bot
from aiogoogle import Aiogoogle

import json
import discord
import argparse
import ipaddress

parser = argparse.ArgumentParser(description='Use this to set bot settings.')
parser.add_argument('-nt', '--not-testing', action='store_false', dest='testing')
parser.add_argument(
    '--host',
    type=lambda ip: ipaddress.IPv4Address('127.0.0.1' if ip == 'localhost' else ip),
    default='localhost'
)

config = parser.parse_args()

engine = create_async_engine(f"sqlite+aiosqlite:///{'test.db' if config.testing else 'bot.db'}")

bot = Bot(command_prefix='/', intents=discord.Intents(messages=True, guilds=True))
# slash = SlashCommand(bot, sync_commands=True)
slash = SlashCommand(bot)

with open('credentials.json') as file:
    client_creds = json.load(file)['web']
    client_creds['scopes'] = ['https://www.googleapis.com/auth/documents']
    aio_google = Aiogoogle(client_creds=client_creds)

from .commands import CommandsCog

bot.add_cog(CommandsCog(bot))

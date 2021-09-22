from . import bot, engine, client_creds
from .server import start_server
from .logs import setUpLogger
from sqlalchemy import text
from .tables import mapper

import asyncio
import logging
import pathlib

logger = logging.getLogger(__name__)

bot.tables_created = asyncio.Event()

@bot.event
async def on_ready():
    async with engine.begin() as conn:
        await conn.execute(text('PRAGMA foreign_keys=ON'))
        await conn.run_sync(mapper.metadata.create_all)
    bot.tables_created.set()

    logger.debug(f"{bot.user} is ready to roll.")

def main():
    logs_dir = pathlib.Path('logs')
    logs_dir.mkdir(exist_ok=True)
    for logger_name in ('teckla.server', 'teckla.commands', '__main__'):
        setUpLogger(f"{logger_name}", logs_dir=logs_dir)

    bot.loop.create_task(start_server())
    bot.run(client_creds['bot-token'])

if __name__ == '__main__':
    main()

from .server import start_server
from dotenv import load_dotenv
from sqlalchemy import text
from .tables import mapper
from . import bot, engine

import os
import asyncio

load_dotenv()

bot.tables_created = asyncio.Event()

@bot.event
async def on_ready():
    async with engine.begin() as conn:
        await conn.execute(text('PRAGMA foreign_keys=ON'))
        await conn.run_sync(mapper.metadata.create_all)
    bot.tables_created.set()

    print(f"{bot.user} is ready to roll.")

def main():
    bot.loop.create_task(start_server())
    bot.run(os.environ['testing-token'])

if __name__ == '__main__':
    main()

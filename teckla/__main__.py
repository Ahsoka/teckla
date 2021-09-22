from . import bot, engine, client_creds
from .server import start_server
from sqlalchemy import text
from .tables import mapper

import asyncio

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
    bot.run(client_creds['bot-token'])

if __name__ == '__main__':
    main()

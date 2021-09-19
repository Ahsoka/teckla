from .server import start_server
from dotenv import load_dotenv
from . import bot

import os

load_dotenv()

@bot.event
async def on_ready():
    print(f"{bot.user} is ready to roll.")

def main():
    bot.loop.create_task(start_server())
    bot.run(os.environ['testing-token'])

if __name__ == '__main__':
    main()

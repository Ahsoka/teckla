from discord_slash.utils.manage_commands import create_option
from discord_slash.cog_ext import cog_slash
from discord.ext.commands import Cog, Bot
from discord_slash import SlashContext

import discord


class CommandsCog(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @cog_slash(
        name='upload',
        description="Upload the messages in the selected channel to a Google Doc.",
        options=[
            create_option(
                'messages',
                "Selects the number of messages to be uploaded, if there is no input all messages will be retrieved.",
                int,
                required=False
            ),
            create_option(
                'channel',
                "Select the channel to upload messages from, if there is no input the current channel is selected.",
                7,
                required=False
            )
        ]
    )
    async def upload(self, ctx: SlashContext, messages: int = None, channel: discord.TextChannel = None):
        if channel is None:
            channel = ctx.channel
        await ctx.defer()
        with open('messages.txt', 'w', encoding='UTF-8') as file:
            async for message in channel.history(limit=messages):
                file.write(f"{message.author} {format(message.created_at, '%m/%d/%Y')}\n{message.content}\n\n")
        await ctx.send('Uploaded content!')

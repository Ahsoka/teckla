from discord_slash.utils.manage_commands import create_option
from discord_slash.cog_ext import cog_slash
from discord.ext.commands import Cog, Bot
from discord_slash import SlashContext
from . import aio_google, client_creds
from typing import Dict

import discord
import secrets

states: Dict[str, int] = {}


class CommandsCog(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @cog_slash(
        name='authenticate',
        description='Register your Google account so you can use the other commands.'
    )
    async def authenticate(self, ctx: SlashContext):
        if aio_google.oauth2.is_ready(client_creds):
            state = secrets.token_urlsafe()
            states[state] = ctx.author.id
            auth_url = aio_google.oauth2.authorization_url(access_type='offline', state=state)

            # This is a workaround for https://github.com/omarryhan/aiogoogle/issues/72
            if (loc := auth_url.find('&include_granted_scopes=null')) != -1:
                auth_url = auth_url[:loc] + auth_url[loc + len('&include_granted_scopes=null'):]

            await ctx.send(f'Please authenticate yourself at this URL: {auth_url}.', hidden=True)
        else:
            await ctx.send('⚠ Uh oh! Something went wrong on our end, please try again later.')
            # TODO: Send message to @Ahsoka to fix it.

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

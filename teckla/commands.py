from discord_slash.utils.manage_commands import create_option
from sqlalchemy.ext.asyncio import AsyncSession
from . import aio_google, client_creds, engine
from discord_slash.cog_ext import cog_slash
from discord.ext.commands import Cog, Bot
from discord_slash import SlashContext
from aiogoogle import Aiogoogle
from typing import Dict, Tuple
from datetime import datetime
from .tables import Token

import asyncio
import discord
import secrets
import emoji

states: Dict[str, Tuple[int, asyncio.Event]]  = {}


class CommandsCog(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def is_authenticated(self, ctx: SlashContext):
        async with AsyncSession(engine) as sess:
            token: Token = await sess.get(Token, ctx.author.id)
        if token and token.expiry < datetime.today():
            await ctx.send(
                'Your token is no longer valid, please use `/authenticate` to refresh your token.'
            )
        elif token:
            return token
        else:
            await ctx.send(
                (
                    "Before you can use this command you must first use the "
                    "`/authenticate` command to register your Google account."
                )
            )
        return False

    @cog_slash(
        name='authenticate',
        description='Register your Google account so you can use the other commands.'
    )
    async def authenticate(self, ctx: SlashContext):
        async with AsyncSession(engine) as sess:
            token: Token = await sess.get(Token, ctx.author.id)

        if token and token.expiry > datetime.today():
            await ctx.send('You are already authenticated!', hidden=True)
        else:
            if aio_google.oauth2.is_ready(client_creds):
                state = secrets.token_urlsafe()
                states[state] = (ctx.author.id, asyncio.Event())
                auth_url = aio_google.oauth2.authorization_url(access_type='offline', state=state)

                # This is a workaround for https://github.com/omarryhan/aiogoogle/issues/72
                if (loc := auth_url.find('&include_granted_scopes=null')) != -1:
                    auth_url = auth_url[:loc] + auth_url[loc + len('&include_granted_scopes=null'):]

                await ctx.send(f'Please authenticate yourself at this URL: {auth_url}.', hidden=True)

                await states[state][1].wait()

                await ctx.send((
                        f'{ctx.author.mention}, '
                        'you have successfully authenticated yourself! 🥳'
                    ),
                    hidden=True
                )
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
        if token := await self.is_authenticated(ctx):
            if channel is None:
                channel = ctx.channel
            await ctx.defer()
            user_creds = token.user_creds()

            updates = []
            current_loc = 1
            async for message in channel.history(limit=messages):
                header_text = f"{message.author} {format(message.created_at, '%m/%d/%Y')}\n"
                header = {
                    'insertText': {
                        'text': header_text, 'location': {'index': current_loc}
                    }
                }
                header_format = {
                    'updateTextStyle': {
                        'textStyle': {
                            'bold': True,
                        },
                        'fields': 'bold',
                        'range': {
                            'startIndex': current_loc,
                            'endIndex': current_loc + len(header_text)
                        }
                    }
                }
                updates.append(header)
                updates.append(header_format)

                current_loc += len(header_text)

                body_text = f"{message.content}\n\n"
                # NOTE: Weird bug with Google Docs where the first \n is not registered
                # if the last character preceeding the \n is an emoji character
                # Example: '😜\n\n' will only have one enter and not the expected two
                if message.content and emoji.get_emoji_regexp().match(message.content[-1]):
                    body_text += '\n'
                body = {
                    'insertText': {
                        'text': body_text, 'location': {'index': current_loc}
                    }
                }
                updates.append(body)

                current_loc += len(body_text)

            async with Aiogoogle(user_creds=user_creds, client_creds=client_creds) as google:
                docs_v1 = await google.discover('docs', 'v1')

                document = await google.as_user(
                    docs_v1.documents.create(data={'title': 'Testing :D'}),
                    full_res=True
                )

                await google.as_user(docs_v1.documents.batchUpdate(
                    documentId=document.content['documentId'],
                    json={'requests': updates}
                ))

            await ctx.send(f"Successfully uploaded to **{document.content['title']}**.")

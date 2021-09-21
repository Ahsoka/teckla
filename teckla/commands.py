from discord_slash.utils.manage_commands import create_option, create_permission
from . import aio_google, client_creds, engine, config
from sqlalchemy.ext.asyncio import AsyncSession
from discord.ext.commands import Cog, Bot
from typing import Dict, Iterable, Tuple
from aiogoogle.resource import GoogleAPI
from discord_slash import SlashContext
from .tables import Token, Document
from discord.ext.tasks import loop
from discord_slash import cog_ext
from aiogoogle import Aiogoogle
from datetime import datetime
from sqlalchemy import select

import contextlib
import aiogoogle
import asyncio
import discord
import secrets
import emoji

states: Dict[str, Tuple[int, asyncio.Event]]  = {}

if config.testing:
    ladyalpha_perm_decorator = lambda func: func
else:
    ladyalpha_perm_decorator = cog_ext.permission(
        809089261100859402,
        [
            create_permission(809185433241387051, 1, True),
            create_permission(809196070587334657, 1, False),
            create_permission(832351220840136745, 1, False),
        ]
    )


class CommandsCog(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @Cog.listener()
    async def on_ready(self):
        if not self.stream_loop.is_running():
            # NOTE: Prevent loop from starting if tables
            # aren't created yet.
            await self.bot.tables_created.wait()
            self.stream_loop.start()

    async def is_authenticated(self, ctx: SlashContext):
        async with AsyncSession(engine) as sess:
            token: Token = await sess.get(Token, ctx.author.id)
        if token and token.expiry < datetime.today():
            await ctx.send(
                'Your token is no longer valid, please use `/authenticate register` to refresh your token.'
            )
        elif token:
            return token
        else:
            await ctx.send(
                (
                    "Before you can use this command you must first use the "
                    "`/authenticate register` command to register your Google account."
                )
            )
        return False

    @cog_ext.cog_subcommand(
        base='authenticate',
        name='register',
        description='Register your Google account so you can use the other commands.',
        options=[]
    )
    @ladyalpha_perm_decorator
    async def authenticate(self, ctx: SlashContext, force: bool = False):
        async with AsyncSession(engine) as sess:
            token: Token = await sess.get(Token, ctx.author.id)

        if token and token.expiry > datetime.today() and token.valid and not force:
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

    @cog_ext.cog_subcommand(
        base='authenticate',
        name='force',
        description="Use this to refresh your access token even if you already have one in the database."
    )
    @ladyalpha_perm_decorator
    async def auth_force(self, ctx: SlashContext):
        await self.authenticate.invoke(ctx, force=True)

    def messages_to_doc_json(self, messages: Iterable[discord.Message]):
        updates = []
        current_loc = 1
        for message in messages:
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
            body_format = {
                'updateTextStyle': {
                    'textStyle': {
                        'bold': False,
                    },
                    'fields': 'bold',
                    'range': {
                        'startIndex': current_loc,
                        'endIndex': current_loc + len(body_text)
                    }
                }
            }
            updates.append(body)
            updates.append(body_format)

            current_loc += len(body_text)

        return updates

    @cog_ext.cog_slash(
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
            ),
            create_option(
                'name',
                "Name for the new document.",
                str,
                required=False
            )
        ]
    )
    @ladyalpha_perm_decorator
    async def upload(self, ctx: SlashContext, messages: int = None, channel: discord.TextChannel = None, name: str = None):
        if channel is None:
            channel = ctx.channel
        if not channel.permissions_for(ctx.me).read_message_history:
            await ctx.send(f"🛑 Uh oh! I can't read {channel.mention}. Please give me permission to read it.")
        elif token := await self.is_authenticated(ctx):
            await ctx.defer()
            user_creds = token.user_creds()

            updates = self.messages_to_doc_json(await channel.history(limit=messages).flatten())

            async with Aiogoogle(user_creds=user_creds, client_creds=client_creds) as google:
                docs_v1 = await google.discover('docs', 'v1')

                kwarg = {'data': {'title': name}} if name else {}
                document = await google.as_user(
                    docs_v1.documents.create(**kwarg),
                    full_res=True
                )

                await google.as_user(docs_v1.documents.batchUpdate(
                    documentId=document.content['documentId'],
                    json={'requests': updates}
                ))

            await ctx.send(f"Successfully uploaded to **{document.content['title']}**.")

    @cog_ext.cog_slash(
        name='stream',
        description='Upload the messages in the selected channel to a Google Doc everyday.',
        options=[
            create_option(
                'channel',
                "Select the channel to upload messages from, if there is no input the current channel is selected.",
                7,
                required=False
            ),
            create_option(
                'name',
                "Name for the new document.",
                str,
                required=False
            )
        ]
    )
    @ladyalpha_perm_decorator
    async def stream(self, ctx: SlashContext, channel: discord.TextChannel = None, name: str = None):
        if channel is None:
            channel = ctx.channel
        if not channel.permissions_for(ctx.me).read_message_history:
            await ctx.send(f"🛑 Uh oh! I can't read {channel.mention}. Please give me permission to read it.")
        elif token := await self.is_authenticated(ctx):
            await ctx.defer()
            async with Aiogoogle(user_creds=token.user_creds(), client_creds=client_creds) as google:
                docs_v1 = await google.discover('docs', 'v1')
                kwarg = {'data': {'title': name}} if name else {}
                document = await google.as_user(docs_v1.documents.create(**kwarg), full_res=True)
                async with AsyncSession(engine) as sess, sess.begin():
                    message: discord.Message = await channel.fetch_message(channel.last_message_id)
                    sess.add(Document(
                        doc_id=document.content['documentId'],
                        channel_id=channel.id,
                        last_message=message.id,
                        last_message_date=message.created_at,
                        discord_id=ctx.author.id
                    ))

            await ctx.send(f"{channel.mention} will now be streamed to **{document.content['title']}**.")

    async def update(self, doc: Document, google: Aiogoogle, docs_v1: GoogleAPI, sess: AsyncSession):
        channel: discord.TextChannel = self.bot.get_channel(doc.channel_id)
        try:
            message = await channel.fetch_message(doc.last_message)
        except (discord.NotFound, discord.HTTPException):
            message = None
        after = message if message else doc.last_message_date

        messages = await channel.history(limit=None, after=after, oldest_first=False).flatten()
        updates = self.messages_to_doc_json(messages)

        if updates:
            try:
                await google.as_user(docs_v1.documents.batchUpdate(
                    documentId=doc.doc_id,
                    json={'requests': updates}
                ))
                doc.last_message = messages[0].id
                doc.last_message_date = messages[0].created_at
            except (aiogoogle.excs.AuthError, aiogoogle.excs.HTTPError):
                doc.token.valid = False
                await sess.commit()
                await sess.refresh(doc)
                try:
                    user = await self.bot.fetch_user(doc.token.id)
                except (discord.NotFound, discord.HTTPException):
                    user = None
                if user:
                    await user.send(
                        ('Your authentication token is no longer valid, '
                        'please refresh it with the `/authenticate register` command.')
                    )

    timer = loop(seconds=10) if config.testing else loop(minutes=2)
    @timer
    async def stream_loop(self):
        coroutines = []
        googles = []
        print('Streaming like AnneMunition!')
        async with AsyncSession(engine) as sess:
            for token in (await sess.execute(select(Token).where(Token.documents.any()))).scalars().all():
                if token.valid:
                    try:
                        if token.is_expired():
                            user_creds = await aio_google.oauth2.refresh(token.user_creds())
                            token.token = user_creds.access_token
                            token.expiry = user_creds.expires_at
                            if user_creds.refresh_token:
                                token.refresh_token = user_creds.refresh_token
                        else:
                            user_creds = token.user_creds()
                    except (aiogoogle.excs.AuthError, aiogoogle.excs.HTTPError) as error:
                        token.valid = False
                        await sess.commit()
                        await sess.refresh(token)
                        try:
                            user = await self.bot.fetch_user(token.id)
                        except (discord.NotFound, discord.HTTPException):
                            user = None
                        if user:
                            await user.send(
                                ('Your authentication token is no longer valid, '
                                'please refresh it with the `/authenticate register` command.')
                            )
                        continue

                    googles.append(Aiogoogle(user_creds=user_creds, client_creds=client_creds))
                    docs_v1 = await googles[-1].discover('docs', 'v1')
                    for doc in token.documents:
                        channel = self.bot.get_channel(doc.channel_id)
                        if channel.permissions_for(channel.guild.me).read_message_history:
                            coroutines.append(self.update(doc, googles[-1], docs_v1, sess))
                            doc.readable = True
                        elif doc.readable:
                            doc.readable = False
                            await sess.commit()
                            try:
                                await sess.refresh(doc)
                                user = await self.bot.fetch_user(doc.token.id)
                                print(f"{doc.token.id=}")
                            except (discord.NotFound, discord.HTTPException):
                                user = None
                            if user:
                                await user.send(f'I can no longer read messages in {channel.mention}, please give me the read messages permission.')

            async with contextlib.AsyncExitStack() as stack:
                for google in googles:
                    await stack.enter_async_context(google)
                await asyncio.gather(*coroutines)

            await sess.commit()

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
import logging

logger = logging.getLogger(__name__)

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
            create_permission(809089261100859402, 1, False)
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
        if not force:
            logger.info(f'{ctx.author} used the /authenticate register command.')
        async with AsyncSession(engine) as sess:
            token: Token = await sess.get(Token, ctx.author.id)

        if token and token.expiry > datetime.today() and token.valid and not force:
            logger.info(f'{ctx.author} tried to authenticate themself even though they are already authenticated.')
            await ctx.send(
                ('You are already authenticated! '
                'Use `/authenticate force` if you want to override your authentication token.'),
                hidden=True
            )
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
                message = f'Something is wrong with the client credentials.\nclient_creds={client_creds}'
                logger.critical(message)
                await ctx.send('⚠ Uh oh! Something went wrong on our end, please try again later.')
                await (await self.bot.fetch_user(388899325885022211)).send(message)

    @cog_ext.cog_subcommand(
        base='authenticate',
        name='force',
        description="Use this to refresh your access token even if you already have one in the database."
    )
    async def auth_force(self, ctx: SlashContext):
        logger.info(f'{ctx.author} used the /authenticate force command.')
        await self.authenticate.invoke(ctx, force=True)

    def messages_to_doc_json(self, messages: Iterable[discord.Message], current_loc: int = 1):
        updates = []
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
                        'endIndex': current_loc + len(header_text.encode('utf-16-le')) // 2
                    }
                }
            }
            updates.append(header)
            updates.append(header_format)

            current_loc += len(header_text.encode('utf-16-le')) // 2

            body_text = f"{message.content}\n\n"
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
                        'endIndex': current_loc + len(body_text.encode('utf-16-le')) // 2
                    }
                }
            }
            updates.append(body)
            updates.append(body_format)

            current_loc += len(body_text.encode('utf-16-le')) // 2

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
        logger.info(f'{ctx.author} used the /upload command to upload {channel}.')
        if not channel.permissions_for(ctx.me).read_message_history:
            logger.warning(f'{ctx.author} failed using the /upload command since the bot cannot read the select channel {channel}.')
            await ctx.send(f"🛑 Uh oh! I can't read {channel.mention}. Please give me permission to read it.")
        elif token := await self.is_authenticated(ctx):
            await ctx.defer()
            user_creds = token.user_creds()

            updates = self.messages_to_doc_json(await channel.history(limit=messages, oldest_first=True).flatten())

            async with Aiogoogle(user_creds=user_creds, client_creds=client_creds) as google:
                docs_v1 = await google.discover('docs', 'v1')

                document = await google.as_user(
                    docs_v1.documents.create(data={'title': name if name else str(channel)}),
                    full_res=True
                )
                logger.info(
                    (f"A Google Doc titled {document.content['title']} "
                    f"was successfully created for {ctx.author}.")
                )

                await google.as_user(docs_v1.documents.batchUpdate(
                    documentId=document.content['documentId'],
                    json={'requests': updates}
                ))

                logger.info(
                    (f"The previous created Google Doc titled {document.content['title']} "
                    f"was successfully updated for {ctx.author}.")
                )

            await ctx.send(f"Successfully uploaded to **{document.content['title']}**.")

    @cog_ext.cog_subcommand(
        base='stream',
        name='new',
        description='Upload the messages in the selected channel to a new Google Doc.',
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
    async def stream_new(self, ctx: SlashContext, channel: discord.TextChannel = None, name: str = None):
        await self.stream(ctx, channel=channel, name=name)

    @cog_ext.cog_subcommand(
        base='stream',
        name='existing',
        description='Upload the messages in the selected channel to an existing Google Doc.',
        options=[
            create_option(
                'document-id',
                "ID for existing Google Document.",
                str,
                required=True
            ),
            create_option(
                'channel',
                "Select the channel to upload messages from, if there is no input the current channel is selected.",
                7,
                required=False
            )
        ],
        connector={'document-id': 'doc_id'}
    )
    async def stream_existing(self, ctx: SlashContext, doc_id: str, channel: discord.TextChannel = None):
        await self.stream(ctx, channel=channel, doc_id=doc_id)

    async def stream(self, ctx: SlashContext, channel: discord.TextChannel = None, name: str = None, doc_id: str = None):
        if name is not None and doc_id is not None:
            raise TypeError('doc_id and name cannot both be passed in.')

        if channel is None:
            channel = ctx.channel
        logger.info(f"{ctx.author} used the /stream command to stream {channel}.")
        if not channel.permissions_for(ctx.me).read_message_history:
            logger.warning(f"{ctx.author} failed using the /stream command since the bot could not read the selected channel.")
            await ctx.send(f"🛑 Uh oh! I can't read {channel.mention}. Please give me permission to read it.")
        elif token := await self.is_authenticated(ctx):
            await ctx.defer()
            async with Aiogoogle(user_creds=token.user_creds(), client_creds=client_creds) as google:
                docs_v1 = await google.discover('docs', 'v1')
                if doc_id:
                    document = await google.as_user(
                        docs_v1.documents.get(documentId=doc_id),
                        full_res=True
                    )
                else:
                    document = await google.as_user(
                        docs_v1.documents.create(data={'title': name if name else str(channel)}),
                        full_res=True
                    )

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

        messages = await channel.history(limit=None, after=after).flatten()

        if messages:
            try:
                await sess.refresh(doc)
                document = await google.as_user(
                    docs_v1.documents.get(documentId=doc.doc_id),
                    full_res=True
                )
                current = 1
                if body := document.content.get('body'):
                    if content := body.get('content'):
                        if content and 'paragraph' in content[-1]:
                            current = content[-1]['endIndex'] - 1
                updates = self.messages_to_doc_json(messages, current_loc=current)
                await google.as_user(docs_v1.documents.batchUpdate(
                    documentId=doc.doc_id,
                    json={'requests': updates}
                ))
                logger.debug(f"Successfully updated {doc.doc_id} with {len(messages)} message(s).")
                doc.last_message = messages[-1].id
                doc.last_message_date = messages[-1].created_at
            except aiogoogle.excs.HTTPError as error:
                logger.warning(f"Failed to updated {doc.doc_id} with {len(messages)} message(s).", exc_info=error)
                discord_id = doc.token.id
                if error.res.status_code == 404:
                    user_message = (
                        f"The document used for streaming <#{doc.channel_id}> has been deleted. "
                        f"Streaming for <#{doc.channel_id}> will now stop, use /stream to restart with a new document."
                    )
                    log_message = (
                        'Detected deleted document, document has been deleted from database and '
                        '{user} has been notified about the missing document.'
                    )
                    await sess.delete(doc)
                else:
                    doc.token.valid = False
                    user_message = (
                        'Your authentication token is no longer valid, '
                        'please refresh it with the `/authenticate register` command.'
                    )
                    log_message = "Successfully notified {user} about a potentially invalid token."
                await sess.commit()

                try:
                    user = await self.bot.fetch_user(discord_id)
                except discord.HTTPException:
                    user = None
                if user:
                    await user.send(user_message)
                    logger.info(log_message.format(user=user))
        else:
            logger.debug(f"No updates detected for {doc.doc_id}.")

    timer = loop(seconds=10) if config.testing else loop(minutes=2)
    @timer
    async def stream_loop(self):
        coroutines = []
        googles = []
        logger.debug('Streaming like AnneMunition!')
        async with AsyncSession(engine) as sess:
            for token in (await sess.execute(select(Token).where(Token.documents.any()))).scalars().all():
                if token.valid:
                    try:
                        if token.is_expired():
                            logger.warning(f'Detected an expired token for {token.id}.')
                            user_creds = await aio_google.oauth2.refresh(token.user_creds())
                            logger.info(f"Successfully refreshed {token.id}'s token.")
                            token.token = user_creds.access_token
                            token.expiry = datetime.fromisoformat(user_creds.expires_at)
                            if user_creds.refresh_token:
                                token.refresh_token = user_creds.refresh_token
                        else:
                            user_creds = token.user_creds()
                    except (aiogoogle.excs.AuthError, aiogoogle.excs.HTTPError) as error:
                        logger.warning(f"Detected invalid token for {token.id}", exc_info=error)
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
                            logger.info(f'Successfully notified {user} ({token.id}) about the invalid token.')
                        continue

                    googles.append(Aiogoogle(user_creds=user_creds, client_creds=client_creds))
                    docs_v1 = await googles[-1].discover('docs', 'v1')
                    for doc in token.documents:
                        channel = self.bot.get_channel(doc.channel_id)
                        if channel.permissions_for(channel.guild.me).read_message_history:
                            coroutines.append(self.update(doc, googles[-1], docs_v1, sess))
                            doc.readable = True
                        elif doc.readable:
                            logger.warning(f"Detected channel {channel} ({channel.id}) that the bot can longer read.")
                            doc.readable = False
                            await sess.commit()
                            try:
                                await sess.refresh(doc)
                                user = await self.bot.fetch_user(doc.token.id)
                            except (discord.NotFound, discord.HTTPException):
                                user = None
                            if user:
                                await user.send(f'I can no longer read messages in {channel.mention}, please give me the read messages permission.')
                                logger.info(
                                    (f'Successfully notified {user} ({doc.token.id}) '
                                    f'about the issue with {channel} ({channel.id}).')
                                )

            async with contextlib.AsyncExitStack() as stack:
                for google in googles:
                    await stack.enter_async_context(google)
                await asyncio.gather(*coroutines)

            await sess.commit()

    @stream_loop.error
    async def handle_stream_loop_error(self, error: Exception):
        logger.critical('stream_loop task crashed due to:', exc_info=error)
        await (await self.bot.fetch_user(388899325885022211)).send(
            f'Bot crashed due to the following error: ```\n{repr(error)}```'
        )

    @cog_ext.cog_slash(
        name='source',
        description="Use this to get the link to the bot's source code!"
    )
    async def source(self, ctx: SlashContext):
        logger.info(f'{ctx.author} used the /source command.')
        await ctx.send('View the source code here: https://github.com/Ahsoka/teckla')

    @Cog.listener()
    async def on_slash_command_error(self, ctx: SlashContext, error: Exception):
        message = f"The following error occured with the {ctx.name} command:"

        logger.critical(message, exc_info=error)

        await ctx.send('⚠ Uh oh! Something went wrong on our end, please try again later.')

        await (await self.bot.fetch_user(388899325885022211)).send(f"{message}```\n{error!r}```")

from sqlalchemy.ext.asyncio import AsyncSession
from .tables import Token, Scope
from . import aio_google, engine
from .commands import states

import aiohttp.web
import dateutil.parser

app = aiohttp.web.Application()
routes = aiohttp.web.RouteTableDef()

async def start_server():
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, 'localhost')
    await site.start()

@routes.get('/')
async def get_creds(request: aiohttp.web.Request):
    if (state := request.query.get('state')) in states:
        full_user_creds = await aio_google.oauth2.build_user_creds(request.query.get('code'))
        async with AsyncSession(engine) as sess, sess.begin():
            discord_id = states[state][0]
            sess.add(Token(
                id=discord_id,
                token=full_user_creds['access_token'],
                expiry=dateutil.parser.isoparse(full_user_creds['expires_at']),
                scopes=list(map(lambda scope: Scope(discord_id, scope), full_user_creds['scopes']))
            ))
        states[state][1].set()
    return aiohttp.web.Response(text="Hello world! 😉")

app.add_routes(routes)

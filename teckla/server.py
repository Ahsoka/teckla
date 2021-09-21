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
            access_token = full_user_creds['access_token']
            refresh_token = full_user_creds['refresh_token']
            expiry = dateutil.parser.isoparse(full_user_creds['expires_at'])
            scopes = list(map(lambda scope: Scope(discord_id, scope), full_user_creds['scopes']))

            token: Token = await sess.get(Token, discord_id)

            if token:
                token.token = access_token
                if token.refresh_token is None or refresh_token is not None:
                    token.refresh_token = refresh_token
                token.expiry = expiry
                token.scopes = scopes
                token.valid = True
            else:
                sess.add(Token(id=discord_id, token=access_token, expiry=expiry, scopes=scopes, refresh_token=refresh_token))
        states[state][1].set()
        del states[state]

        return aiohttp.web.Response(text='Congratulations, you have successfully authenticated! You may close this window.')
    else:
        return aiohttp.web.Response(body="Authentication failed, please using the /authenticate register command again.")

app.add_routes(routes)

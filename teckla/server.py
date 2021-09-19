import aiohttp.web

app = aiohttp.web.Application()
routes = aiohttp.web.RouteTableDef()

async def start_server():
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, 'localhost')
    await site.start()

@routes.get('/')
async def get_creds(request: aiohttp.web.Request):
    print(f"{request=}")

app.add_routes(routes)

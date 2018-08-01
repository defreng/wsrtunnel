import asyncio
from asyncio import sleep

import pytest
from aiohttp import web, WSServerHandshakeError

from client import main
from server import RelayServer


@pytest.fixture
def wsserver():
    app = web.Application()
    RelayServer().add_routes(app)

    return app


@pytest.fixture
def service():
    async def test_handler(request):
        return web.Response(status=200, text='contenttext')

    async def wait_handler(request):
        number = int(request.match_info.get('number', 1))
        await sleep(1 + number % 3)

        return web.Response(status=200, text=str(number))

    async def return_headers(request):
        headers = list(filter(lambda x: x[0].startswith('My'), request.headers.items()))

        return web.json_response(tuple(request.headers.items()), headers=headers, status=200)

    async def post_method(request):
        if request.method == 'POST':
            data = await request.json()
            return web.json_response(data, status=200)
        return web.Response(status=500)

    async def binary_data(request):
        return web.Response(body=b'\x00\x01\x02\xff', status=200)

    async def status302(request):
        return web.Response(status=302)

    app = web.Application()
    app.add_routes([web.get('/test', test_handler)])
    app.add_routes([web.get('/headers', return_headers)])
    app.add_routes([web.get('/serve_wait/{number}', wait_handler)])
    app.add_routes([web.get('/binary', binary_data)])
    app.add_routes([web.get('/status302', status302)])
    app.add_routes([web.post('/post', post_method)])

    return app


class AsyncServiceStackContext:
    def __init__(self, aiohttp_server, aiohttp_client, gateway_service, target_service):
        self.aiohttp_server = aiohttp_server
        self.aiohttp_client = aiohttp_client

        self.gateway_service = gateway_service
        self.target_service = target_service

    async def wait_for_gateway_connection(self):
        while True:
            response = await self.client.get('/test', timeout=5)
            if response.status != 502:
                return response

            await sleep(1)

    async def __aenter__(self):
        self.service_server = await self.aiohttp_server(self.target_service)
        self.service_server_base_url = str(self.service_server._root)

        # start our wsserver (including a client to access it)
        self.client = await self.aiohttp_client(self.gateway_service)
        self.gateway_websocket_url = str(self.client.server.make_url('/_ws'))

        # start our wsclient
        self.gateway_client_task = asyncio.create_task(main(
            self.gateway_websocket_url, self.service_server_base_url))

        response = await self.wait_for_gateway_connection()
        assert 200 == response.status
        assert 'contenttext' == await response.text()

        return self.client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.gateway_client_task.cancel()


@pytest.fixture
def mock_service_context(aiohttp_server, aiohttp_client, wsserver, service):
    return AsyncServiceStackContext(aiohttp_server, aiohttp_client, wsserver, service)


async def test_service_unavailable(aiohttp_client, wsserver):
    client = await aiohttp_client(wsserver)

    for i in range(5):
        response = await client.get('/api/test')
        assert response.status == 502

        await sleep(0.2)


async def test_consecutive_wsclient_connections(aiohttp_client, wsserver):
    client = await aiohttp_client(wsserver)

    ws = await client.ws_connect('/_ws')
    assert ws.exception() is None
    await ws.close()

    ws = await client.ws_connect('/_ws')
    assert ws.exception() is None
    await ws.close()


async def test_single_request(mock_service_context):
    async with mock_service_context:
        assert True


async def test_concurrent_request(mock_service_context):
    async with mock_service_context as client:
        tasks = []
        for i in range(5):
            tasks.append(asyncio.create_task(client.get('/serve_wait/' + str(i))))

        finished, pending = await asyncio.wait(tasks, timeout=20)
        assert len(tasks) == len(finished)

        for i, task in enumerate(tasks):
            assert 200 == task.result().status
            assert str(i) == await task.result().text()


async def test_two_wsclients(aiohttp_client, wsserver):
    client1 = await aiohttp_client(wsserver)
    client2 = await aiohttp_client(wsserver)

    ws1 = None
    ws2 = None
    try:
        ws1 = await client1.ws_connect('/_ws')
        assert ws1.exception() is None

        with pytest.raises(WSServerHandshakeError) as e:
            await client2.ws_connect('/_ws')
        assert e.value.status == 409
    finally:
        if ws1 is not None and not ws1.closed:
            await ws1.close()
        if ws2 is not None and not ws1.closed:
            await ws2.close()


async def test_multiheaders(mock_service_context):
    async with mock_service_context as client:
        headers = [
            ['MyHeader', '1'],
            ['MyHeader', '2'],
            ['MyHeader', '3'],
        ]
        response = await client.get('/headers', headers=headers)

        myheaders = list(filter(lambda x: x[0].startswith('My'), await response.json()))
        assert ['MyHeader', '1'] == myheaders[0]
        assert ['MyHeader', '2'] == myheaders[1]
        assert ['MyHeader', '3'] == myheaders[2]

        response_headers = list(filter(lambda x: x[0].startswith('My'), response.headers.items()))
        assert ('MyHeader', '1') == response_headers[0]
        assert ('MyHeader', '2') == response_headers[1]
        assert ('MyHeader', '3') == response_headers[2]


async def test_post(mock_service_context):
    testdata = {
        'test1': True,
        'test2': 2,
        'test3': 'str'
    }

    async with mock_service_context as client:
        response = await client.post('/post', json=testdata)
        assert 200 == response.status
        data = await response.json()
        assert testdata == data


async def test_binary(mock_service_context):
    async with mock_service_context as client:
        response = await client.get('/binary')
        assert 200 == response.status
        assert b'\x00\x01\x02\xff' == await response.read()


async def test_status_codes(mock_service_context):
    async with mock_service_context as client:
        response = await client.get('/status302')
        assert 302 == response.status

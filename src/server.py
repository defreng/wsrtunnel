import argparse
import dataclasses
import json
import uuid

import binascii

import asyncio
from asyncio import Future

import logging

import multidict
from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import StreamResponse

from common import WrappedRequest, WrappedResponse


RESPONSE_TIMEOUT_MS = 600 * 1000

HOP_BY_HOP_HEADERS = (
    'Connection',
    'Keep-Alive',
    'Public',
    'Proxy-Authenticate',
    'Transfer-Encoding',
    'Upgrade',
)


logger_proxy_server = logging.getLogger('proxy_server')


class RelayServer:
    def __init__(self):
        self.ws = None

        self.responses = dict()
        self.responses_finalized = dict()

    async def request_server(self, request: Request):
        guid = str(uuid.uuid4())
        wrapped_request = await WrappedRequest.from_request(guid, request)

        if self.ws is None:
            return web.Response(status=502, text='502 - Service not available')

        try:
            self.responses[guid] = response = StreamResponse()
            response.original_request = request
            self.responses_finalized[guid] = response_finalized = Future()

            await self.ws.send_json(dataclasses.asdict(wrapped_request))
            await asyncio.wait_for(response_finalized, timeout=RESPONSE_TIMEOUT_MS)

            await response.write_eof()

            return response
        finally:
            if guid in self.responses: del self.responses[guid]
            if guid in self.responses_finalized: del self.responses_finalized[guid]

    async def websocket_server(self, request):
        if self.ws is not None:
            logger_proxy_server.warning('Denying new client, as one is already connected')
            return web.Response(status=409, text='409 - Other client already connected')

        try:
            ws = web.WebSocketResponse()
            await ws.prepare(request)

            self.ws = ws

            async for msg in self.ws:
                wrapped_response = WrappedResponse.from_data(json.loads(msg.data))

                response = self.responses.get(wrapped_response.guid, None)
                if response is not None:
                    if not response.prepared:
                        headers = multidict.MultiDict(wrapped_response.headers)

                        for hbh_header in HOP_BY_HOP_HEADERS:
                            if hbh_header in headers:
                                del headers[hbh_header]

                        response.headers.update(headers)
                        response.set_status(wrapped_response.status)
                        await response.prepare(response.original_request)

                    await response.write(binascii.a2b_base64(wrapped_response.content))
                    self.responses_finalized[wrapped_response.guid].set_result(True)
                else:
                    logger_proxy_server.warning('Got response with unknown ID. ')
        finally:
            self.ws = None

    def add_routes(self, app):
        app.add_routes([web.get('/_ws', self.websocket_server)])
        app.add_routes([web.route('*', '/{path:.*}', self.request_server)])


if __name__ == '__main__':
    app = web.Application()
    rs = RelayServer()
    rs.add_routes(app)

    parser = argparse.ArgumentParser(description="websocket relay server")
    parser.add_argument('--path', default='/tmp/wsrtunnel.sock')

    args = parser.parse_args()
    web.run_app(app, path=args.path)

import argparse
import dataclasses
import json
from urllib.parse import urlparse

import aiohttp
import asyncio

import binascii

import logging
from aiohttp import TraceConfig
from multidict import CIMultiDict

from common import WrappedResponse, WrappedRequest


handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)

logger_proxy_client = logging.getLogger('proxy_client')
logger_proxy_client.setLevel(logging.DEBUG)
logger_proxy_client.addHandler(handler)

logger_requests = logging.getLogger('requests')
logger_requests.setLevel(logging.DEBUG)
logger_requests.addHandler(handler)


async def on_request_start(session, trace_config_ctx, params):
    logger_requests.info(f'> {params.method:>4} {params.url.path_qs}')


async def connect_ws(ws_session, websocket_url, service_session, service_base_url, websocket_proxy=None):
    async with ws_session.ws_connect(websocket_url, proxy=websocket_proxy) as ws:
        logger_proxy_client.info(f'WS CONNECTED: {websocket_url}')

        async for msg in ws:
            request = WrappedRequest.from_data(json.loads(msg.data))

            url = service_base_url + request.path
            headers = CIMultiDict(request.headers)
            headers['Host'] = urlparse(service_base_url).hostname

            async with service_session.request(request.method, url, data=binascii.a2b_base64(request.data),
                                               headers=headers, ssl=False) as response:
                response = await WrappedResponse.from_response(request.guid, response)

                await ws.send_json(dataclasses.asdict(response))


async def main(websocket_url, service_base_url, websocket_proxy=None):
    trace_config = TraceConfig()
    trace_config.on_request_start.append(on_request_start)

    async with aiohttp.ClientSession() as gateway_server_session, \
            aiohttp.ClientSession(trace_configs=[trace_config]) as service_session:
        while True:
            try:
                await connect_ws(gateway_server_session, websocket_url, service_session, service_base_url,
                                 websocket_proxy=websocket_proxy)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger_proxy_client.error(e)

            logger_proxy_client.info('WS DISCONNECTED: waiting 10 seconds for reconnect')
            await asyncio.sleep(10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='wsrtunnel client')
    parser.add_argument('--service-url', type=str, required=True,
                        help='[REQUIRED] URL of the target service the end-user of this proxy wants to access.')
    parser.add_argument('--gateway-url', type=str, required=True,
                        help='[REQUIRED] URL of the gateway server (websocket connection)')
    parser.add_argument('--gateway-proxy-url', type=str,
                        help='HTTP proxy sitting between this client and the gateway server')

    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(args.gateway_url, args.service_url, websocket_proxy=args.gateway_proxy_url))
    loop.run_until_complete(asyncio.sleep(0.250))
    loop.close()

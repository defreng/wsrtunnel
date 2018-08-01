import binascii
from dataclasses import dataclass

from aiohttp import ClientResponse
from aiohttp.web_request import Request


@dataclass(frozen=True)
class WrappedRequest:
    guid: str
    method: str
    path: str
    headers: tuple
    data: str

    @staticmethod
    async def from_request(guid: str, request: Request):
        return WrappedRequest(
            guid=guid,
            method=request.method,
            path=request.path_qs,
            headers=tuple(((header[0].decode('ascii'), header[1].decode('ascii'))for header in request.raw_headers)),
            data=binascii.b2a_base64(await request.read()).decode('ascii')
        )

    @staticmethod
    def from_data(data: dict):
        return WrappedRequest(
            guid=data['guid'],
            method=data['method'],
            path=data['path'],
            headers=data['headers'],
            data=data['data']
        )


@dataclass(frozen=True)
class WrappedResponse:
    guid: str
    status: int
    headers: tuple
    content: str

    @staticmethod
    async def from_response(guid:str, response: ClientResponse):
        return WrappedResponse(
            guid=guid,
            status=response.status,
            headers=tuple(((header[0].decode('ascii'), header[1].decode('ascii'))for header in response.raw_headers)),
            content=binascii.b2a_base64(await response.read()).decode('ascii')
        )

    @staticmethod
    def from_data(data: dict):
        return WrappedResponse(
            guid=data['guid'],
            status=data['status'],
            headers=data['headers'],
            content=data['content']
        )

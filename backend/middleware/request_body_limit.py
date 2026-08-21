"""ASGI request-body limits that count the bytes actually received."""

import logging
from tempfile import SpooledTemporaryFile

from starlette.requests import Request
from starlette.responses import JSONResponse

from constants import DEFAULT_BODY_SIZE_LIMIT, FILE_UPLOAD_BODY_LIMIT
from middleware.rate_limit import (
    apply_cors_headers,
    get_request_client_ip,
    hash_client_ip,
)

logger = logging.getLogger(__name__)


def request_body_limit_for_path(method: str, path: str) -> int:
    """Return the route-aware limit used by both header and streamed-body checks."""
    path_parts = path.strip("/").split("/")
    is_kb_document_upload = (
        method.upper() == "POST"
        and len(path_parts) == 6
        and path_parts[0] == "api"
        and path_parts[1] == "tenants"
        and bool(path_parts[2])
        and path_parts[3] == "knowledge_bases"
        and bool(path_parts[4])
        and path_parts[5] == "documents"
    )
    if path == "/api/v1/files:upload" or is_kb_document_upload:
        return FILE_UPLOAD_BODY_LIMIT
    return DEFAULT_BODY_SIZE_LIMIT


class RequestBodyLimitMiddleware:
    """Reject oversized bodies using Content-Length and actual ASGI body chunks."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        max_size = request_body_limit_for_path(request.method, request.url.path)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_size:
                    await self._reject(request, max_size, receive, send)
                    return
            except ValueError:
                # An invalid header is not trusted; the chunk counter remains authoritative.
                pass

        # Read and count the ASGI stream before route parsing. A spooled file keeps
        # normal JSON in memory and rolls larger multipart bodies to temporary disk.
        received = 0
        disconnected = False
        body_file = SpooledTemporaryFile(max_size=1024 * 1024)
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                disconnected = True
                break
            if message["type"] != "http.request":
                continue

            chunk = message.get("body", b"")
            received += len(chunk)
            if received > max_size:
                body_file.close()
                await self._reject(request, max_size, receive, send)
                return
            body_file.write(chunk)
            if not message.get("more_body", False):
                break

        if disconnected:
            body_file.close()
            return

        body_file.seek(0)
        remaining = received
        replay_complete = False

        async def replay_receive():
            nonlocal remaining, replay_complete
            if replay_complete:
                # StreamingResponse keeps listening for a real disconnect after
                # the request body is consumed. Delegate instead of cancelling SSE.
                return await receive()

            chunk = body_file.read(min(64 * 1024, remaining)) if remaining else b""
            remaining -= len(chunk)
            replay_complete = remaining == 0
            return {
                "type": "http.request",
                "body": chunk,
                "more_body": not replay_complete,
            }

        try:
            await self.app(scope, replay_receive, send)
        finally:
            body_file.close()

    @staticmethod
    async def _reject(request: Request, max_size: int, receive, send) -> None:
        logger.warning(
            "Request too large from client_hash=%s",
            hash_client_ip(get_request_client_ip(request)),
        )
        response = JSONResponse(
            status_code=413,
            content={
                "detail": f"请求体过大，最大允许 {max_size // (1024 * 1024)}MB"
            },
        )
        apply_cors_headers(request, response)
        await response(request.scope, receive, send)

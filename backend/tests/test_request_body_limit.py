"""Request-body limits must count bytes even without Content-Length."""

import pytest

from constants import DEFAULT_BODY_SIZE_LIMIT, FILE_UPLOAD_BODY_LIMIT
from middleware.request_body_limit import (
    RequestBodyLimitMiddleware,
    request_body_limit_for_path,
)


def test_route_aware_limits_match_upload_contract():
    assert (
        request_body_limit_for_path("POST", "/api/v1/files:upload")
        == FILE_UPLOAD_BODY_LIMIT
    )
    assert (
        request_body_limit_for_path(
            "POST", "/api/tenants/tenant-1/knowledge_bases/kb-1/documents"
        )
        == FILE_UPLOAD_BODY_LIMIT
    )
    assert (
        request_body_limit_for_path("POST", "/api/admin/login")
        == DEFAULT_BODY_SIZE_LIMIT
    )


@pytest.mark.asyncio
async def test_chunked_request_over_limit_is_rejected(public_client):
    async def oversized_body():
        yield b"{" + b"x" * (DEFAULT_BODY_SIZE_LIMIT // 2)
        yield b"x" * (DEFAULT_BODY_SIZE_LIMIT // 2 + 1) + b"}"

    response = await public_client.post(
        "/api/admin/login",
        headers={
            "Origin": "https://client.example",
            "Content-Type": "application/json",
        },
        content=oversized_body(),
    )

    assert response.status_code == 413
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert "请求体过大" in response.json()["detail"]


@pytest.mark.asyncio
async def test_content_length_over_limit_still_rejects_before_body_read(public_client):
    response = await public_client.post(
        "/api/admin/login",
        headers={
            "Origin": "https://client.example",
            "Content-Length": str(DEFAULT_BODY_SIZE_LIMIT + 1),
            "Content-Type": "application/json",
        },
        content=b"{}",
    )

    assert response.status_code == 413
    assert response.headers["Access-Control-Allow-Origin"] == "*"


@pytest.mark.asyncio
async def test_disconnect_before_complete_body_does_not_enter_application():
    application_called = False

    async def application(scope, receive, send):
        nonlocal application_called
        application_called = True

    middleware = RequestBodyLimitMiddleware(application)

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        raise AssertionError(f"unexpected response after disconnect: {message}")

    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/admin/login",
            "raw_path": b"/api/admin/login",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "http_version": "1.1",
        },
        receive,
        send,
    )

    assert application_called is False

import hashlib
import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from middleware.rate_limit import RateLimitMiddleware, apply_cors_headers, should_apply_rate_limit
from services.redis_service import RedisService


class _DummyApp:
    async def __call__(self, scope, receive, send):
        return None


@pytest.mark.asyncio
async def test_get_redis_reuses_service_in_same_loop(monkeypatch):
    middleware = RateLimitMiddleware(_DummyApp(), use_redis=True)
    fake_service = object()
    call_count = 0

    async def fake_get_redis():
        nonlocal call_count
        call_count += 1
        return fake_service

    monkeypatch.setattr("services.redis_service.get_redis", fake_get_redis)

    first = await middleware._get_redis()
    second = await middleware._get_redis()

    assert first is fake_service
    assert second is fake_service
    assert call_count == 1


@pytest.mark.asyncio
async def test_get_redis_falls_back_to_memory_on_failure(monkeypatch):
    middleware = RateLimitMiddleware(_DummyApp(), use_redis=True)

    async def failing_get_redis():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("services.redis_service.get_redis", failing_get_redis)

    redis_service = await middleware._get_redis()

    assert redis_service is None
    assert middleware.use_redis is False
    assert middleware._redis_service is None
    assert middleware._redis_loop_id is None


@pytest.mark.asyncio
async def test_check_rate_limit_uses_memory_after_redis_failure(monkeypatch):
    middleware = RateLimitMiddleware(_DummyApp(), use_redis=True, requests_per_minute=3, burst_size=3)

    async def failing_get_redis():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("services.redis_service.get_redis", failing_get_redis)

    allowed_1, remaining_1 = await middleware._check_rate_limit("127.0.0.1")
    allowed_2, remaining_2 = await middleware._check_rate_limit("127.0.0.1")

    assert allowed_1 is True
    assert allowed_2 is True
    assert remaining_1 == 2
    assert remaining_2 == 1
    assert middleware.use_redis is False


@pytest.mark.asyncio
async def test_check_rate_limit_disables_redis_after_runtime_failure(monkeypatch):
    middleware = RateLimitMiddleware(
        _DummyApp(), use_redis=True, requests_per_minute=3, burst_size=3
    )

    class FailingRedis:
        async def check_rate_limit(self, *args, **kwargs):
            raise RuntimeError("redis://user:secret@redis:6379 unavailable")

    async def fake_get_redis():
        return FailingRedis()

    monkeypatch.setattr(middleware, "_get_redis", fake_get_redis)

    allowed, remaining = await middleware._check_rate_limit("127.0.0.1")

    assert allowed is True
    assert remaining == 2
    assert middleware.use_redis is False


@pytest.mark.asyncio
async def test_check_rate_limit_reports_redis_backend_on_success(monkeypatch):
    middleware = RateLimitMiddleware(_DummyApp(), use_redis=True)

    class HealthyRedis:
        async def check_rate_limit(self, *args, **kwargs):
            return False, 0

    async def fake_get_redis():
        return HealthyRedis()

    monkeypatch.setattr(middleware, "_get_redis", fake_get_redis)

    allowed, remaining, backend = await middleware._check_rate_limit_with_backend(
        "127.0.0.1"
    )

    assert allowed is False
    assert remaining == 0
    assert backend == "redis"
    assert middleware.use_redis is True


def _request_with_client_and_headers(client_ip, headers):
    app = FastAPI()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(name.lower().encode(), value.encode()) for name, value in headers.items()],
        "client": (client_ip, 12345),
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "app": app,
    }
    return Request(scope)


def test_get_client_ip_ignores_forwarded_headers_from_untrusted_peer():
    middleware = RateLimitMiddleware(
        FastAPI(), use_redis=False, trusted_proxy_cidrs="10.0.0.0/8"
    )
    request = _request_with_client_and_headers(
        "198.51.100.7",
        {
            "X-Forwarded-For": "203.0.113.10",
            "X-Real-IP": "203.0.113.11",
        },
    )

    assert middleware._get_client_ip(request) == "198.51.100.7"


def test_get_client_ip_accepts_forwarded_ip_from_trusted_proxy():
    middleware = RateLimitMiddleware(
        FastAPI(), use_redis=False, trusted_proxy_cidrs="172.16.0.0/12"
    )
    request = _request_with_client_and_headers(
        "172.17.0.2", {"X-Forwarded-For": "203.0.113.10"}
    )

    assert middleware._get_client_ip(request) == "203.0.113.10"


def test_get_client_ip_walks_forwarded_chain_from_trusted_edge():
    middleware = RateLimitMiddleware(
        FastAPI(),
        use_redis=False,
        trusted_proxy_cidrs="10.0.0.0/8,172.16.0.0/12",
    )
    request = _request_with_client_and_headers(
        "172.17.0.2",
        {"X-Forwarded-For": "192.0.2.99, 203.0.113.10, 10.0.0.8"},
    )

    assert middleware._get_client_ip(request) == "203.0.113.10"


def test_get_client_ip_falls_back_to_peer_for_malformed_forwarded_header():
    middleware = RateLimitMiddleware(
        FastAPI(), use_redis=False, trusted_proxy_cidrs="172.16.0.0/12"
    )
    request = _request_with_client_and_headers(
        "172.17.0.2", {"X-Forwarded-For": "not-an-ip"}
    )

    assert middleware._get_client_ip(request) == "172.17.0.2"


@pytest.mark.asyncio
async def test_rate_limit_log_hashes_client_ip_and_records_backend(caplog):
    app = FastAPI()

    @app.get("/api/v1/chat")
    async def ping():
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=1,
        burst_size=1,
        use_redis=False,
    )
    client_ip = "127.0.0.1"
    expected_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:12]

    with caplog.at_level(logging.WARNING, logger="middleware.rate_limit"):
        transport = ASGITransport(app=app, client=(client_ip, 12345))
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            await client.get("/api/v1/chat")
            response = await client.get("/api/v1/chat")

    assert response.status_code == 429
    assert client_ip not in caplog.text
    assert f"client_hash={expected_hash}" in caplog.text
    assert "backend=memory" in caplog.text
    assert "path=/api/v1/chat" in caplog.text


@pytest.mark.asyncio
async def test_redis_rate_limit_failure_is_not_silently_allowed(caplog):
    service = object.__new__(RedisService)

    class FailingPipeline:
        def zremrangebyscore(self, *args):
            return self

        def zcard(self, *args):
            return self

        def zadd(self, *args):
            return self

        def expire(self, *args):
            return self

        async def execute(self):
            raise RuntimeError("redis://user:secret@redis:6379 unavailable")

    class FailingClient:
        def pipeline(self):
            return FailingPipeline()

    service.client = FailingClient()

    with caplog.at_level(logging.WARNING, logger="services.redis_service"):
        with pytest.raises(RuntimeError):
            await service.check_rate_limit("rate:ip:test", max_requests=3)

    assert "secret" not in caplog.text


def test_redis_initialization_log_does_not_expose_connection_url(monkeypatch, caplog):
    redis_url = "redis://user:secret@redis:6379/0"
    monkeypatch.setattr("services.redis_service.settings.redis_url", redis_url)

    with caplog.at_level(logging.INFO, logger="services.redis_service"):
        RedisService()

    assert "Redis service initialized" in caplog.text
    assert redis_url not in caplog.text
    assert "secret" not in caplog.text


def test_apply_cors_headers_echoes_allowed_origin(monkeypatch):
    monkeypatch.setattr("middleware.rate_limit.settings.allowed_origins", "https://client.example")
    monkeypatch.setattr("middleware.rate_limit.settings.cors_allow_null_origin", False)
    response = JSONResponse(status_code=429, content={"detail": "rate limited"})

    app = FastAPI()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"origin", b"https://client.example")],
        "client": ("127.0.0.1", 12345),
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
    }
    request = Request(scope)

    apply_cors_headers(request, response)

    assert response.headers["Access-Control-Allow-Origin"] == "https://client.example"
    assert response.headers["Access-Control-Allow-Methods"]
    assert response.headers["Access-Control-Allow-Headers"]
    assert response.headers["Vary"] == "Origin"


def test_apply_cors_headers_no_origin(monkeypatch):
    """Missing Origin header should not get wildcard CORS."""
    monkeypatch.setattr("middleware.rate_limit.settings.cors_allow_null_origin", False)
    response = JSONResponse(status_code=429, content={"detail": "rate limited"})

    app = FastAPI()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
    }
    request = Request(scope)

    apply_cors_headers(request, response)
    assert "Access-Control-Allow-Origin" not in response.headers


def test_should_apply_rate_limit_only_for_public_client_endpoints():
    app = FastAPI()

    limited_paths = [
        "/api/v1/chat",
        "/api/v1/chat/stream",
        "/api/v1/chat/messages",
        "/api/v1/contexts",
        "/api/v1/config:public",
    ]
    exempt_paths = [
        "/api/admin/login",
        "/api/admin/register",
        "/api/admin/me",
        "/api/v1/agent",
        "/api/v1/agent:default",
        "/api/v1/urls:list",
        "/api/v1/index:status",
        "/health",
    ]

    for path in limited_paths:
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": path,
                "headers": [],
                "client": ("127.0.0.1", 12345),
                "query_string": b"",
                "scheme": "http",
                "server": ("testserver", 80),
                "app": app,
            }
        )
        assert should_apply_rate_limit(request) is True

    for path in exempt_paths:
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": path,
                "headers": [],
                "client": ("127.0.0.1", 12345),
                "query_string": b"",
                "scheme": "http",
                "server": ("testserver", 80),
                "app": app,
            }
        )
        assert should_apply_rate_limit(request) is False


@pytest.mark.asyncio
async def test_options_requests_bypass_rate_limit():
    app = FastAPI()

    @app.get("/api/v1/chat/messages")
    async def get_messages():
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=1,
        burst_size=1,
        use_redis=False,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        preflight_1 = await client.options(
            "/api/v1/chat/messages",
            headers={
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        preflight_2 = await client.options(
            "/api/v1/chat/messages",
            headers={
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        get_response = await client.get("/api/v1/chat/messages")
        limited_response = await client.get("/api/v1/chat/messages")

    assert preflight_1.status_code in [200, 405]
    assert preflight_2.status_code in [200, 405]
    assert get_response.status_code == 200
    assert limited_response.status_code == 429


@pytest.mark.asyncio
async def test_rate_limited_response_keeps_cors_headers(monkeypatch):
    monkeypatch.setattr("middleware.rate_limit.settings.allowed_origins", "*")
    monkeypatch.setattr("middleware.rate_limit.settings.cors_allow_null_origin", False)
    app = FastAPI()

    @app.get("/api/v1/chat")
    async def ping():
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=1,
        burst_size=1,
        use_redis=False,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        allowed = await client.get("/api/v1/chat", headers={"Origin": "https://client.example"})
        limited = await client.get("/api/v1/chat", headers={"Origin": "https://client.example"})

    assert allowed.status_code == 200
    assert limited.status_code == 429
    assert limited.headers["Access-Control-Allow-Origin"] == "*"
    assert limited.headers["X-RateLimit-Limit"] == "1"
    assert limited.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_admin_endpoints_bypass_rate_limit():
    app = FastAPI()

    @app.get("/api/v1/agent")
    async def get_agent():
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=1,
        burst_size=1,
        use_redis=False,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.get("/api/v1/agent")
        second = await client.get("/api/v1/agent")

    assert first.status_code == 200
    assert second.status_code == 200
    assert "X-RateLimit-Limit" not in second.headers


@pytest.mark.asyncio
async def test_public_client_endpoints_still_rate_limited():
    app = FastAPI()

    @app.get("/api/v1/chat/messages")
    async def get_messages():
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=1,
        burst_size=1,
        use_redis=False,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.get("/api/v1/chat/messages")
        second = await client.get("/api/v1/chat/messages")

    assert first.status_code == 200
    assert second.status_code == 429

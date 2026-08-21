"""Regression tests for admin auth protection on management endpoints."""

import pytest

from api.endpoints import auth as auth_endpoints


@pytest.fixture(autouse=True)
def clear_login_fallback_history():
    auth_endpoints._login_attempt_history.clear()
    yield
    auth_endpoints._login_attempt_history.clear()


def test_login_memory_fallback_records_first_attempt(monkeypatch):
    monkeypatch.setattr(auth_endpoints.time, "time", lambda: 100.0)

    allowed, retry_after = auth_endpoints._check_login_rate_limit(
        "198.51.100.10", max_attempts=3, window_seconds=60
    )

    assert allowed is True
    assert retry_after == 0
    assert list(auth_endpoints._login_attempt_history["198.51.100.10"]) == [100.0]


def test_login_memory_fallback_blocks_at_limit_and_isolates_ips(monkeypatch):
    monkeypatch.setattr(auth_endpoints.time, "time", lambda: 200.0)

    assert auth_endpoints._check_login_rate_limit("198.51.100.10", 2, 60)[0]
    assert auth_endpoints._check_login_rate_limit("198.51.100.10", 2, 60)[0]

    allowed, retry_after = auth_endpoints._check_login_rate_limit(
        "198.51.100.10", 2, 60
    )
    assert allowed is False
    assert retry_after == 61
    assert auth_endpoints._check_login_rate_limit("198.51.100.11", 2, 60)[0]


def test_login_memory_fallback_allows_after_window_expires(monkeypatch):
    now = 300.0
    monkeypatch.setattr(auth_endpoints.time, "time", lambda: now)

    assert auth_endpoints._check_login_rate_limit("198.51.100.10", 1, 60)[0]
    assert not auth_endpoints._check_login_rate_limit("198.51.100.10", 1, 60)[0]

    now = 361.0
    allowed, retry_after = auth_endpoints._check_login_rate_limit(
        "198.51.100.10", 1, 60
    )
    assert allowed is True
    assert retry_after == 0
    assert list(auth_endpoints._login_attempt_history["198.51.100.10"]) == [361.0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("get", "/api/v1/sources:summary", None),
    ],
)
async def test_management_endpoints_require_auth(
    public_client, default_agent_id, method, path, json_body
):
    kwargs = {"json": json_body} if json_body is not None else {}
    response = await getattr(public_client, method)(
        f"{path}?agent_id={default_agent_id}",
        **kwargs,
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("post", "/api/v1/chat", {"message": "hello"}),
        ("get", "/api/v1/config:public", None),
        ("post", "/api/v1/contexts", {"query": "test"}),
    ],
)
async def test_public_endpoints_remain_accessible(
    public_client, default_agent_id, method, path, json_body
):
    kwargs = {}
    if method == "post":
        kwargs["json"] = {"agent_id": default_agent_id, **(json_body or {})}
    response = await getattr(public_client, method)(
        f"{path}?agent_id={default_agent_id}" if method == "get" else path,
        **kwargs,
    )
    assert response.status_code not in (401, 403)

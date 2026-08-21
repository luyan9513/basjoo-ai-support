"""Liveness stays shallow while readiness reports required local dependencies."""

import pytest

from services import readiness_service


@pytest.mark.asyncio
async def test_dependency_exception_is_reported_as_unavailable():
    async def failing_check():
        raise RuntimeError("sensitive dependency detail")

    name, available = await readiness_service._run_check("redis", failing_check)

    assert name == "redis"
    assert available is False


@pytest.mark.asyncio
async def test_readiness_returns_200_when_all_dependencies_are_ready(
    public_client, monkeypatch
):
    async def all_ready():
        return {
            "sqlite": True,
            "redis": True,
            "qdrant": True,
            "scrapling": True,
        }

    monkeypatch.setattr("main.check_readiness", all_ready)

    response = await public_client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "sqlite": "ok",
            "redis": "ok",
            "qdrant": "ok",
            "scrapling": "ok",
        },
    }


@pytest.mark.asyncio
async def test_readiness_returns_503_without_leaking_dependency_error(
    public_client, monkeypatch
):
    async def redis_unavailable():
        return {
            "sqlite": True,
            "redis": False,
            "qdrant": True,
            "scrapling": True,
        }

    monkeypatch.setattr("main.check_readiness", redis_unavailable)

    response = await public_client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "sqlite": "ok",
            "redis": "unavailable",
            "qdrant": "ok",
            "scrapling": "ok",
        },
    }


@pytest.mark.asyncio
async def test_liveness_does_not_depend_on_readiness(public_client, monkeypatch):
    async def all_unavailable():
        return {
            "sqlite": False,
            "redis": False,
            "qdrant": False,
            "scrapling": False,
        }

    monkeypatch.setattr("main.check_readiness", all_unavailable)

    response = await public_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

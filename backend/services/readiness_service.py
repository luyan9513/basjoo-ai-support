"""Readiness checks for the local services required by the main application path."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx
from sqlalchemy import text

import database
from config import settings
from services.redis_service import get_redis
from services.scrapling_client import get_scrapling_client

logger = logging.getLogger(__name__)

CHECK_TIMEOUT_SECONDS = 5


async def _check_sqlite() -> bool:
    async with database.AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    return True


async def _check_redis() -> bool:
    redis = await get_redis()
    return await redis.health_check()


async def _check_qdrant() -> bool:
    headers = {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else {}
    async with httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS) as client:
        response = await client.get(
            f"{settings.qdrant_url.rstrip('/')}/readyz",
            headers=headers,
        )
    return response.status_code == 200


async def _check_scrapling() -> bool:
    return await get_scrapling_client().health_check()


async def _run_check(
    name: str, checker: Callable[[], Awaitable[bool]]
) -> tuple[str, bool]:
    try:
        result = await asyncio.wait_for(checker(), timeout=CHECK_TIMEOUT_SECONDS)
        return name, bool(result)
    except Exception as error:
        logger.warning(
            "Readiness dependency unavailable: dependency=%s error_type=%s",
            name,
            type(error).__name__,
        )
        return name, False


async def check_readiness() -> dict[str, bool]:
    """Check required local dependencies concurrently without leaking error details."""
    checks = {
        "sqlite": _check_sqlite,
        "redis": _check_redis,
        "qdrant": _check_qdrant,
        "scrapling": _check_scrapling,
    }
    results = await asyncio.gather(
        *(_run_check(name, checker) for name, checker in checks.items())
    )
    return dict(results)


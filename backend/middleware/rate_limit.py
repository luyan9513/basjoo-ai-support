"""
API级速率限制中间件

支持两种模式：
1. Redis 分布式限流（生产环境）
2. 内存限流（开发/测试环境）
"""

from collections import defaultdict, deque
import hashlib
import ipaddress
import logging
import time
from typing import Deque, Dict, Optional, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from config import settings

logger = logging.getLogger(__name__)

PUBLIC_RATE_LIMIT_PATH_PREFIXES = (
    "/api/v1/chat",
    "/api/v1/contexts",
    "/api/v1/config:public",
)


def _append_vary_header(response: Response, value: str) -> None:
    """Append a value to the Vary header without duplicating it."""
    existing = response.headers.get("Vary")
    if not existing:
        response.headers["Vary"] = value
        return

    values = [item.strip() for item in existing.split(",") if item.strip()]
    if value not in values:
        response.headers["Vary"] = ", ".join([*values, value])


def apply_cors_headers(request: Request, response: Response) -> Response:
    """Apply CORS headers for early middleware responses that bypass CORSMiddleware."""
    origin = request.headers.get("origin")

    # No Origin header -> no CORS needed (non-browser/server-to-server requests)
    if origin is None or origin == "":
        return response

    # Handle Origin: null (e.g., file:// protocol) only if explicitly allowed
    if origin == "null":
        if settings.cors_allow_null_origin:
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = settings.allowed_methods
            response.headers["Access-Control-Allow-Headers"] = settings.allowed_headers
        return response

    allowed_origins = settings.cors_origins_list
    if "*" in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = settings.allowed_methods
        response.headers["Access-Control-Allow-Headers"] = settings.allowed_headers
        return response

    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = settings.allowed_methods
        response.headers["Access-Control-Allow-Headers"] = settings.allowed_headers
        _append_vary_header(response, "Origin")

    return response


def _parse_trusted_proxy_networks(value: str):
    networks = []
    for candidate in value.split(","):
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid trusted proxy CIDR")
    return networks


def _parse_ip(value: str):
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _is_trusted_proxy(address, networks) -> bool:
    return address is not None and any(address in network for network in networks)


def hash_log_identifier(value: str) -> str:
    """Return a short irreversible identifier suitable for operational logs."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def hash_client_ip(client_ip: str) -> str:
    return hash_log_identifier(client_ip)


def get_request_client_ip(
    request: Request,
    trusted_proxy_cidrs: str | None = None,
) -> str:
    """Resolve client IP without trusting forwarding headers from arbitrary peers."""
    peer_host = request.client.host if request.client and request.client.host else "unknown"
    peer_ip = _parse_ip(peer_host)
    if peer_ip is None:
        return peer_host

    networks = _parse_trusted_proxy_networks(
        settings.trusted_proxy_cidrs
        if trusted_proxy_cidrs is None
        else trusted_proxy_cidrs
    )
    if not _is_trusted_proxy(peer_ip, networks):
        return str(peer_ip)

    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        chain = []
        for candidate in forwarded.split(","):
            address = _parse_ip(candidate)
            if address is None:
                return str(peer_ip)
            chain.append(address)

        for address in reversed(chain):
            if not _is_trusted_proxy(address, networks):
                return str(address)

    real_ip = _parse_ip(request.headers.get("X-Real-IP", ""))
    if real_ip is not None:
        return str(real_ip)

    return str(peer_ip)


def should_apply_rate_limit(request: Request) -> bool:
    """Apply rate limiting only to public client-facing endpoints."""
    if request.method == "OPTIONS":
        return False

    path = request.url.path
    return path.startswith(PUBLIC_RATE_LIMIT_PATH_PREFIXES)


def check_memory_sliding_window(
    history_map: Dict[str, Deque[float]],
    key: str,
    *,
    max_requests: int,
    window_seconds: int,
) -> Tuple[bool, int]:
    """Shared in-memory sliding-window limiter.

    Keeps only timestamps inside the window and returns remaining capacity.
    """
    now = time.time()
    history = history_map.get(key)
    if history is None:
        history = deque()
        history_map[key] = history

    while history and now - history[0] >= window_seconds:
        history.popleft()

    if not history:
        history_map.pop(key, None)
        history = deque()
        history_map[key] = history

    if len(history) >= max_requests:
        return False, 0

    history.append(now)
    remaining = max(0, max_requests - len(history))
    return True, remaining


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    速率限制中间件

    支持 Redis 分布式限流和内存限流两种模式
    """

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        burst_size: int = 10,
        use_redis: bool = True,
        trusted_proxy_cidrs: str | None = None,
    ):
        """
        初始化速率限制中间件

        Args:
            app: FastAPI应用实例
            requests_per_minute: 每分钟允许的最大请求数
            burst_size: 短时间内允许的突发请求数
            use_redis: 是否使用 Redis（生产环境推荐）
        """
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.use_redis = use_redis
        self.trusted_proxy_cidrs = (
            settings.trusted_proxy_cidrs
            if trusted_proxy_cidrs is None
            else trusted_proxy_cidrs
        )

        # 内存限流的备用存储
        self.request_history: Dict[str, Deque[float]] = defaultdict(deque)
        self.burst_counters: Dict[str, int] = defaultdict(int)
        self.last_burst_reset: float = time.time()

        # Redis 服务（延迟初始化，按事件循环隔离）
        self._redis_service = None
        self._redis_loop_id: Optional[int] = None

    async def _get_redis(self):
        """获取 Redis 服务（延迟初始化）"""
        if not self.use_redis:
            return None

        try:
            import asyncio
            from services.redis_service import get_redis

            loop_id = id(asyncio.get_running_loop())
            if self._redis_service is None or self._redis_loop_id != loop_id:
                self._redis_service = await get_redis()
                self._redis_loop_id = loop_id
        except Exception:
            logger.warning(
                "rate_limit_backend_fallback backend=memory reason=redis_unavailable"
            )
            self.use_redis = False
            self._redis_service = None
            self._redis_loop_id = None

        return self._redis_service

    async def dispatch(self, request: Request, call_next):
        """处理每个请求"""
        if not should_apply_rate_limit(request):
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        # 检查速率限制
        allowed, remaining, backend = await self._check_rate_limit_with_backend(client_ip)

        if not allowed:
            logger.warning(
                "rate_limit_exceeded client_hash=%s backend=%s path=%s",
                hash_client_ip(client_ip),
                backend,
                request.url.path,
            )
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "请求过于频繁，请稍后再试",
                    "error": "rate_limit_exceeded",
                },
            )
            response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
            response.headers["X-RateLimit-Remaining"] = "0"
            return apply_cors_headers(request, response)

        # 处理请求
        response = await call_next(request)

        # 添加速率限制头
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response

    def _get_client_ip(self, request: Request) -> str:
        """获取客户端IP地址"""
        return get_request_client_ip(request, self.trusted_proxy_cidrs)

    async def _check_rate_limit(self, ip: str) -> Tuple[bool, int]:
        """
        检查是否超过速率限制

        Args:
            ip: 客户端IP地址

        Returns:
            (是否允许, 剩余请求数)
        """
        allowed, remaining, _backend = await self._check_rate_limit_with_backend(ip)
        return allowed, remaining

    async def _check_rate_limit_with_backend(self, ip: str) -> Tuple[bool, int, str]:
        """Check the limit and report which backend made the decision."""
        redis = await self._get_redis()
        if redis:
            try:
                key = f"rate:ip:{ip}"
                allowed, remaining = await redis.check_rate_limit(
                    key,
                    max_requests=self.requests_per_minute,
                    window_seconds=60,
                )
                return allowed, remaining, "redis"
            except Exception:
                logger.warning(
                    "rate_limit_backend_fallback backend=memory reason=redis_error"
                )
                self.use_redis = False
                self._redis_service = None
                self._redis_loop_id = None

        # 使用内存限流
        allowed, remaining = self._check_memory_rate_limit(ip)
        return allowed, remaining, "memory"

    def _check_memory_rate_limit(self, ip: str) -> Tuple[bool, int]:
        """
        内存限流（备用方案）

        Args:
            ip: 客户端IP地址

        Returns:
            (是否允许, 剩余请求数)
        """
        current_time = time.time()

        # 检查突发限制
        if current_time - self.last_burst_reset > 1:  # 每秒重置突发计数
            self.burst_counters.clear()
            self.last_burst_reset = current_time

        if self.burst_counters[ip] >= self.burst_size:
            logger.debug(
                "burst_rate_limit_exceeded client_hash=%s", hash_client_ip(ip)
            )
            return False, 0

        allowed, remaining = check_memory_sliding_window(
            self.request_history,
            ip,
            max_requests=self.requests_per_minute,
            window_seconds=60,
        )
        if not allowed:
            logger.debug(
                "minute_rate_limit_exceeded client_hash=%s", hash_client_ip(ip)
            )
            return False, 0

        self.burst_counters[ip] += 1
        return True, remaining

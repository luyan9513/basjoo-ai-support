from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from contextlib import asynccontextmanager
import logging
import os

from config import settings
from database import init_db
from api.endpoints import auth
from api.v1 import endpoints as v1_endpoints
from api.v1 import kb_document_endpoints as v1_kb_doc_endpoints
from api.v1 import agent_run_endpoints as v1_agent_run_endpoints
from services.scheduler import (
    agent_purge_scheduler,
    url_fetch_scheduler,
    history_cleanup_scheduler,
    session_auto_close_scheduler,
)
from services.redis_service import get_redis, close_redis
from middleware import RateLimitMiddleware, RequestBodyLimitMiddleware
from middleware.rate_limit import apply_cors_headers as apply_early_cors_headers
from i18n.core import I18nMiddleware
from services.readiness_service import check_readiness

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    test_mode = os.getenv("BASJOO_TEST_MODE") == "1"

    logger.info("初始化数据库...")
    await init_db()
    logger.info("数据库初始化完成")

    if not test_mode:
        # 初始化 Redis 连接
        logger.info("初始化 Redis 连接...")
        try:
            redis = await get_redis()
            if await redis.health_check():
                logger.info("Redis 连接成功")
            else:
                logger.warning("Redis 连接失败，将使用内存限流")
        except Exception as e:
            logger.warning(f"Redis 初始化失败: {e}，将使用内存限流")

        logger.info("启动URL抓取调度器...")
        url_fetch_scheduler.start()
        logger.info("URL抓取调度器已启动")

        logger.info("启动历史记录清理调度器...")
        history_cleanup_scheduler.start()
        logger.info("历史记录清理调度器已启动")

        logger.info("启动会话自动关闭调度器...")
        session_auto_close_scheduler.start()
        logger.info("会话自动关闭调度器已启动")

        logger.info("启动智能体清理调度器...")
        await agent_purge_scheduler.purge_expired_agents()
        agent_purge_scheduler.start()
        logger.info("智能体清理调度器已启动")
    else:
        logger.info("测试模式已启用，跳过 Redis 和调度器启动")

    yield

    if not test_mode:
        logger.info("停止URL抓取调度器...")
        url_fetch_scheduler.stop()
        logger.info("URL抓取调度器已停止")

        logger.info("停止历史记录清理调度器...")
        history_cleanup_scheduler.stop()
        logger.info("历史记录清理调度器已停止")

        logger.info("停止会话自动关闭调度器...")
        session_auto_close_scheduler.stop()
        logger.info("会话自动关闭调度器已停止")

        logger.info("停止智能体清理调度器...")
        agent_purge_scheduler.stop()
        logger.info("智能体清理调度器已停止")

        # 关闭 Redis 连接
        logger.info("关闭 Redis 连接...")
        await close_redis()

    logger.info("应用关闭")


app = FastAPI(
    title=settings.app_name,
    description="智能体（agent）系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=settings.cors_methods_list,
    allow_headers=settings.cors_headers_list,
)


@app.middleware("http")
async def cors_for_file_protocol(request, call_next):
    """Apply the shared early-response CORS policy to normal responses too."""
    response = await call_next(request)
    return apply_early_cors_headers(request, response)


app.add_middleware(I18nMiddleware)

app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=settings.rate_limit_per_minute,
    burst_size=settings.rate_limit_burst_size,
    trusted_proxy_cidrs=settings.trusted_proxy_cidrs,
)


@app.middleware("http")
async def log_requests(request, call_next):
    logger.info(f"REQUEST: {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(
            f"RESPONSE: {response.status_code} {request.method} {request.url.path}"
        )
        return response
    except Exception as e:
        logger.exception(f"ERROR processing {request.method} {request.url.path}: {e}")
        raise


# Keep this pure ASGI middleware outermost so streamed/chunked bodies are counted
# before BaseHTTPMiddleware or route parsing can consume them.
app.add_middleware(RequestBodyLimitMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    """Return JSON for unhandled exceptions instead of plain-text 500."""
    logger = logging.getLogger("uvicorn")
    logger.exception(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}"
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Auth API (kept for frontend login/register)
app.include_router(auth.router, prefix="/api/admin", tags=["auth"])

# v1 API
app.include_router(v1_endpoints.router, tags=["v1"])
app.include_router(v1_kb_doc_endpoints.router, tags=["kb-documents"])
app.include_router(v1_agent_run_endpoints.router)


# SDK.js 路由 - 用于嵌入 widget
@app.get("/sdk.js")
async def get_sdk_js():
    """返回 widget SDK 文件"""
    sdk_path = os.path.join(os.path.dirname(__file__), "static", "sdk.js")
    if os.path.exists(sdk_path):
        return FileResponse(sdk_path, media_type="application/javascript")
    return {"error": "SDK not found"}


# Logo 路由 - 用于聊天窗口显示
@app.get("/basjoo-logo.png")
async def get_logo():
    """返回 widget logo 文件"""
    logo_path = os.path.join(os.path.dirname(__file__), "static", "basjoo-logo.png")
    if os.path.exists(logo_path):
        return FileResponse(logo_path, media_type="image/png")
    return {"error": "Logo not found"}


# Widget 演示页面路由
@app.get("/widget-demo", response_class=HTMLResponse)
async def get_widget_demo():
    """返回 widget 嵌入演示页面"""
    demo_path = os.path.join(os.path.dirname(__file__), "static", "widget-demo.html")
    if os.path.exists(demo_path):
        with open(demo_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Error: Demo page not found</h1>"


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/ready")
async def readiness_check():
    checks = await check_readiness()
    ready = all(checks.values())
    payload = {
        "status": "ready" if ready else "not_ready",
        "checks": {
            name: "ok" if available else "unavailable"
            for name, available in checks.items()
        },
    }
    if ready:
        return payload
    return JSONResponse(status_code=503, content=payload)


@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.app_name} API",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=True,
        log_level=settings.log_level,
    )

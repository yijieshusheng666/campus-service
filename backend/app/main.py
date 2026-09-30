"""FastAPI 应用入口。"""
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import update

from app.api import api_router
from app.api import ws as ws_api
from app.config import settings
from app.core.redis_client import close_redis
from app.database import AsyncSessionLocal
from app.models.resume import ParseStatus, Resume

logger = logging.getLogger("campus")

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

description = """
**校园综合服务平台**：二手交易 + AI 简历 + AI 模拟面试 + 校园跑腿 + 站内私信一体化平台。

- 用户系统：JWT 认证，登录注册统一身份，均可买卖二手与求职
- 二手交易：商品 CRUD、图片上传、分页搜索、收藏、订单
- AI 简历：PDF 上传 → LLM 结构化提取 → AI 优化建议（只诊断不改写，建议持久化）
- AI 模拟面试：选简历+岗位 → LLM 面试官多轮提问（SSE 流式）→ 结构化评估报告
- 校园跑腿：发布快递代拿需求 → 原子抢单 → 送达 → 结算
- 站内私信：WebSocket 实时聊天，消息落库、离线补拉、未读数
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 进程重启会丢失进行中的后台解析任务：遗留 pending 一律标记为 failed，用户可手动重试
    # （分布式模式下任务在 Celery worker 里执行，不受 API 进程重启影响，这里只是兜底）
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Resume)
            .where(Resume.parse_status == ParseStatus.pending)
            .values(parse_status=ParseStatus.failed)
        )
        await db.commit()
    # 分布式模式：启动 WS 推送的 Redis 桥（单机模式下内部直接返回，无副作用）
    await ws_api.start_redis_bridge()
    yield
    await ws_api.stop_redis_bridge()
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    description=description,
    version="0.1.0",
    lifespan=lifespan,
)

# 静态文件：上传的商品图片 / 简历
app.mount(settings.STATIC_URL, StaticFiles(directory=settings.UPLOAD_DIR), name="static")

# CORS：通配符来源与凭证携带不可同时开启（浏览器规范禁止且存在安全隐患）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_origins_list != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由
app.include_router(api_router)

# WebSocket 私信（挂载在根路径 /ws，token 走 query 参数）
app.include_router(ws_api.router)


# ---------------- 请求日志中间件 ----------------
# 记录每个请求的方法、路径、状态码、耗时；/ws 的 query 里带 token，不记 query 防令牌落日志
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %s (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ---------------- 全局异常处理 ----------------
# 未捕获异常统一返回 500 JSON，并把完整堆栈写进日志（journald 收集），
# 避免 FastAPI 默认行为把内部错误细节直接暴露给调用方
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("未捕获异常: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"},
    )


# 确保 application logger 输出到 uvicorn stderr（含 agent trace 等调试信息）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    force=True,
)


@app.get("/health", tags=["系统"])
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}
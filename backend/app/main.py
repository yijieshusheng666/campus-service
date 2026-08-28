"""FastAPI 应用入口。"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import update

from app.api import api_router
from app.api import ws as ws_api
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.resume import ParseStatus, Resume

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
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Resume)
            .where(Resume.parse_status == ParseStatus.pending)
            .values(parse_status=ParseStatus.failed)
        )
        await db.commit()
    yield


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


# 确保 application logger 输出到 uvicorn stderr（含 agent trace 等调试信息）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    force=True,
)


@app.get("/health", tags=["系统"])
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}
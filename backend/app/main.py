"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.config import settings

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

description = """
**校园综合服务平台**：二手交易 + AI 简历一体化平台。

- 用户系统：JWT 认证，登录注册统一身份，均可买卖二手与求职
- 二手交易：商品 CRUD、图片上传、分页搜索、收藏、订单
- AI 简历：PDF 上传 → LLM 结构化提取 → 可视化编辑与 AI 改良
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
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


@app.get("/health", tags=["系统"])
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}
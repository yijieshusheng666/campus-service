"""Redis 客户端（可选组件）。

REDIS_URL 未配置时 get_redis() 返回 None，全系统回落单机模式：
- 后台任务走 asyncio（见 app/core/dispatch.py）
- WebSocket 推送走进程内存（见 app/api/ws.py）
"""
import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis | None:
    """返回全局 async Redis 客户端；未配置 REDIS_URL 时返回 None。"""
    global _client
    if not settings.redis_enabled:
        return None
    if _client is None:
        _client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        logger.info("Redis 已启用: %s", settings.REDIS_URL.split("@")[-1])
    return _client


async def close_redis() -> None:
    """关闭连接（应用关停时调用）。"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None

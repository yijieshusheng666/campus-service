"""Celery 任务队列（分布式模式）。

仅在 REDIS_URL 配置后启用；未配置时 API 走 asyncio 后台任务（见 app/core/dispatch.py），
本模块不会被 import，因此单机环境完全无感。

启动 worker：
    celery -A app.tasks.celery_app worker --loglevel=info --pool=threads --concurrency=4
（docker-compose.yml 的 celery 服务与 deploy/campus-worker.service 均已配好）
"""
import asyncio

from celery import Celery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

celery_app = Celery(
    "campus",
    broker=settings.REDIS_URL or "redis://localhost:6379/0",
    backend=settings.REDIS_URL or "redis://localhost:6379/0",
)
celery_app.conf.update(
    task_acks_late=True,           # 任务执行完才确认：worker 崩溃任务会重新投递，不丢
    worker_prefetch_multiplier=1,  # LLM 任务是长任务，一次只领一个，避免全堆在一个 worker 上
)


@celery_app.task(name="campus.parse_resume", bind=True, max_retries=2, default_retry_delay=30)
def parse_resume_task(self, resume_id: int) -> None:
    """Celery 版简历解析。

    每次执行都新建事件循环和数据库引擎：SQLAlchemy async 引擎的连接池绑定
    创建它的事件循环，跨 asyncio.run() 复用会拿到「挂在上一个循环上」的死连接。
    """

    async def _run() -> None:
        from app.services.resume_parse import parse_resume

        engine = create_async_engine(
            settings.sqlalchemy_url,
            pool_pre_ping=False,  # asyncmy 的 ping 与 SQLAlchemy 方言不兼容（同 app/database.py）
            pool_recycle=3600,
        )
        try:
            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            await parse_resume(resume_id, factory)
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)

"""后台任务调度：有 Redis 时交给 Celery，没有时回落 asyncio 后台任务（单机模式）。

这就是「workers 能多开」的关键开关：
- 单机模式（REDIS_URL 空）：任务在 API 进程内跑，进程重启即丢失（lifespan 会把
  遗留 pending 标记为 failed），所以 workers 只能开 1。
- 分布式模式（REDIS_URL 已配）：任务投递到 Redis 队列，由独立 Celery worker 消费，
  API 进程随便重启、随便扩副本，任务不丢。
"""
import asyncio
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# 后台任务强引用集：事件循环只持弱引用，不保活任务可能被 GC 中途回收
_bg_tasks: set[asyncio.Task] = set()


def spawn_bg(coro) -> None:
    """在事件循环里跑一个后台协程（单机模式的兜底执行器）。"""
    t = asyncio.create_task(coro)
    _bg_tasks.add(t)

    def _on_done(task: asyncio.Task) -> None:
        _bg_tasks.discard(task)
        if not task.cancelled() and task.exception():
            logger.error("后台任务异常: %s", task.exception())

    t.add_done_callback(_on_done)


def enqueue_resume_parse(resume_id: int) -> None:
    """投递简历解析任务：有队列走队列，没队列走进程内后台任务。"""
    if settings.redis_enabled:
        # 延迟 import：未启用 Celery 的单机环境不引入其依赖开销
        from app.tasks import parse_resume_task

        parse_resume_task.delay(resume_id)
        logger.info("简历解析任务已投递 Celery id=%s", resume_id)
    else:
        from app.database import AsyncSessionLocal
        from app.services.resume_parse import parse_resume

        spawn_bg(parse_resume(resume_id, AsyncSessionLocal))
        logger.info("简历解析任务已转 asyncio 后台（单机模式）id=%s", resume_id)

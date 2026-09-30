"""后台任务调度（app/core/dispatch.py）：单机/分布式两条路径的分流逻辑。"""
from app.core import dispatch


def test_enqueue_resume_parse_falls_back_to_asyncio_without_redis(monkeypatch):
    """未配置 REDIS_URL：走 asyncio 后台任务（单机模式），不 import Celery。"""
    monkeypatch.setattr(dispatch.settings, "REDIS_URL", "")

    captured = {}

    def fake_spawn(coro):
        captured["spawned"] = True
        coro.close()  # 不真的执行，关掉协程避免 "never awaited" 警告

    async def fake_parse(resume_id, session_factory):  # pragma: no cover
        pass

    monkeypatch.setattr(dispatch, "spawn_bg", fake_spawn)
    monkeypatch.setattr("app.services.resume_parse.parse_resume", fake_parse)

    dispatch.enqueue_resume_parse(42)
    assert captured.get("spawned") is True


def test_enqueue_resume_parse_uses_celery_with_redis(monkeypatch):
    """配置 REDIS_URL：任务投递到 Celery，不在 API 进程内执行。"""
    monkeypatch.setattr(dispatch.settings, "REDIS_URL", "redis://localhost:6379/0")

    sent = {}

    class FakeTask:
        def delay(self, resume_id):
            sent["resume_id"] = resume_id

    monkeypatch.setattr("app.tasks.parse_resume_task", FakeTask())

    dispatch.enqueue_resume_parse(7)
    assert sent["resume_id"] == 7

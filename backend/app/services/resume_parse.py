"""简历 LLM 结构化解析的执行体。

从 app/api/resumes.py 抽离，供两条执行路径共用：
- 单机模式：API 进程内 asyncio 后台任务（app/core/dispatch.py）
- 分布式模式：Celery worker（app/tasks.py）

session_factory 由调用方传入，因为两条路径的数据库引擎生命周期不同：
API 进程复用全局 AsyncSessionLocal；Celery worker 每次任务新建引擎并在结束后 dispose。
"""
import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.resume import ParseStatus, Resume
from app.services.llm import extract_resume

logger = logging.getLogger(__name__)

SessionFactory = async_sessionmaker[AsyncSession]


async def _mark_parse_failed(session_factory: SessionFactory, resume_id: int) -> None:
    """尽力把简历标记为解析失败；本身再失败只记录日志。"""
    try:
        async with session_factory() as db:
            resume = await db.get(Resume, resume_id)
            if resume:
                resume.parse_status = ParseStatus.failed
                await db.commit()
    except Exception:
        logger.exception("标记解析失败状态时出错 id=%s", resume_id)


async def parse_resume(resume_id: int, session_factory: SessionFactory) -> None:
    """解析任务主体：两段式会话——LLM 调用期间不占用数据库连接。"""
    # 阶段A：仅读取原文并立即释放连接
    async with session_factory() as db:
        resume = await db.get(Resume, resume_id)
        if not resume:
            return
        raw_text = resume.raw_text

    try:
        parsed = await asyncio.to_thread(extract_resume, raw_text)
        if not parsed:
            raise RuntimeError("LLM 返回空结果")
    except Exception:
        logger.exception("简历后台解析失败 id=%s", resume_id)
        await _mark_parse_failed(session_factory, resume_id)
        return

    # 阶段B：写回结果
    try:
        async with session_factory() as db:
            resume = await db.get(Resume, resume_id)
            if not resume:
                return
            resume.parsed_name = parsed.get("name")
            resume.parsed_phone = parsed.get("phone")
            resume.parsed_email = parsed.get("email")
            resume.parsed_location = parsed.get("location")
            resume.parsed_job_title = parsed.get("job_title")
            resume.parsed_education = parsed.get("education") or None
            resume.parsed_skills = parsed.get("skills") or None
            resume.parsed_experience = parsed.get("experience") or None
            resume.parsed_summary = parsed.get("summary")
            resume.parsed_sections = parsed.get("sections") or None
            resume.parse_status = ParseStatus.completed
            await db.commit()
        logger.info("简历后台解析完成 id=%s", resume_id)
    except Exception:
        logger.exception("简历解析结果写回失败 id=%s", resume_id)
        await _mark_parse_failed(session_factory, resume_id)

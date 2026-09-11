"""AI 简历 API：上传 PDF → 提取文本 → LLM 结构化解析、AI 优化建议。"""
import asyncio
import logging
import os
from pathlib import Path

import pdfplumber
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.core.utils import ALLOWED_RESUME_EXT, looks_like_docx, looks_like_pdf, safe_filename
from app.database import AsyncSessionLocal, get_db
from app.models.resume import ParseStatus, Resume
from app.models.user import User
from app.schemas.resume import ResumeAdviceIn, ResumeOut
from app.services.llm import advise_resume, extract_resume

logger = logging.getLogger(__name__)

# 后台任务强引用集：事件循环只持弱引用，不保活任务可能被 GC 中途回收
_bg_tasks: set[asyncio.Task] = set()


def _spawn_bg(coro) -> None:
    t = asyncio.create_task(coro)
    _bg_tasks.add(t)

    def _on_done(task: asyncio.Task) -> None:
        _bg_tasks.discard(task)
        if not task.cancelled() and task.exception():
            logger.error("后台任务异常: %s", task.exception())

    t.add_done_callback(_on_done)


router = APIRouter(prefix="/resumes", tags=["简历"])


def _ensure_resume_dir() -> Path:
    d = Path(settings.UPLOAD_DIR) / "resumes"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _mark_parse_failed(resume_id: int) -> None:
    """尽力把简历标记为解析失败；本身再失败只记录日志。"""
    try:
        async with AsyncSessionLocal() as db:
            resume = await db.get(Resume, resume_id)
            if resume:
                resume.parse_status = ParseStatus.failed
                await db.commit()
    except Exception:
        logger.exception("标记解析失败状态时出错 id=%s", resume_id)


async def _parse_resume_task(resume_id: int) -> None:
    """后台解析任务：两段式会话——LLM 调用期间不占用数据库连接。"""
    # 阶段A：仅读取原文并立即释放连接
    async with AsyncSessionLocal() as db:
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
        await _mark_parse_failed(resume_id)
        return

    # 阶段B：写回结果
    try:
        async with AsyncSessionLocal() as db:
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
        await _mark_parse_failed(resume_id)


def _extract_pdf_text(pdf_path: Path) -> str:
    """同步提取 PDF 全文（CPU/IO 密集，须放入线程池执行）。"""
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _extract_docx_text(docx_path: Path) -> str:
    """提取 Word(.docx) 全文。

    简历非常爱用【表格】排版（基本信息一行三格那种），只遍历 paragraphs
    会把表格里的内容整个漏掉 —— 那样解析出来的简历就缺姓名电话，
    所以表格单元格也必须遍历。
    """
    from docx import Document

    doc = Document(str(docx_path))
    parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text:
                    parts.append(text)
    return "\n".join(parts)


def _build_vector_text(resume: Resume) -> str:
    """构造简历语义向量文本：基础信息 + 动态模块内容 + 介绍。"""
    parts = []
    if resume.parsed_name:
        parts.append(f"姓名：{resume.parsed_name}")
    # 优先使用动态模块结构（含全部板块）
    if resume.parsed_sections:
        for sec in resume.parsed_sections:
            title = sec.get("title") or sec.get("type") or ""
            items = sec.get("items") or []
            blocks = []
            for it in items:
                block = "，".join(
                    x for x in [it.get("heading"), it.get("subheading"), it.get("date")] if x
                )
                if it.get("description"):
                    block = f"{block}\n{it['description']}" if block else it["description"]
                if block:
                    blocks.append(block)
            if blocks:
                parts.append(f"{title}：" + "；".join(blocks))
    else:
        if resume.parsed_education:
            parts.append("教育背景：" + "；".join(map(str, resume.parsed_education)))
        if resume.parsed_skills:
            parts.append("技能：" + "、".join(str(s) for s in resume.parsed_skills))
        if resume.parsed_experience:
            for exp in resume.parsed_experience:
                if isinstance(exp, dict):
                    parts.append(f"经历：{exp.get('company','')}{exp.get('title','')} {exp.get('content','')}")
        if resume.parsed_summary:
            parts.append(f"自我评价：{resume.parsed_summary}")
    if resume.raw_text:
        parts.append("原始内容：" + resume.raw_text[:1500])
    return "\n".join(parts)


def _to_out(resume: Resume) -> ResumeOut:
    out = ResumeOut.model_validate(resume)
    if resume.file_path:
        relative_path = os.path.relpath(resume.file_path, settings.UPLOAD_DIR)
        relative_path = relative_path.replace("\\", "/")
        out.pdf_url = f"{settings.STATIC_URL}/{relative_path}"
    return out


@router.post("/upload", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix == ".doc":
        # 旧版二进制格式，解析要靠外部程序，明确拒绝并告诉用户怎么办，
        # 比含糊地报「仅支持 PDF」体验好得多
        raise HTTPException(
            status_code=400,
            detail="暂不支持旧版 .doc 格式，请用 Word/WPS 另存为 .docx 后再上传",
        )
    if suffix not in ALLOWED_RESUME_EXT:
        raise HTTPException(status_code=400, detail="仅支持 PDF 或 Word(.docx) 简历")

    content = await file.read(settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 1)
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件超过大小限制")

    # 按内容二次校验：扩展名可以随便改，文件头骗不了人
    if suffix == ".pdf" and not looks_like_pdf(content[:16]):
        raise HTTPException(status_code=400, detail="文件内容不是有效的 PDF")
    if suffix == ".docx" and not looks_like_docx(content[:16]):
        raise HTTPException(
            status_code=400,
            detail="文件内容不是有效的 Word 文档（.docx 本质是 ZIP 容器），请确认没有手动改过扩展名",
        )

    # 保存本地
    filename = safe_filename(file.filename or "resume.pdf", prefix="resume_")
    file_path = _ensure_resume_dir() / filename
    file_path.write_bytes(content)

    # 文本提取是同步 IO，放入线程池避免阻塞事件循环；两种格式各走各的解析器
    try:
        if suffix == ".pdf":
            raw_text = await asyncio.to_thread(_extract_pdf_text, file_path)
        else:
            raw_text = await asyncio.to_thread(_extract_docx_text, file_path)
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"文档解析失败：{e}") from e

    if not raw_text.strip():
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="未能从 PDF 中提取到文本内容")

    # 入库为待解析状态并立即返回；LLM 结构化解析转后台任务
    resume = Resume(
        user_id=user.id,
        file_name=file.filename or filename,
        file_path=str(file_path),
        raw_text=raw_text,
        parse_status=ParseStatus.pending,
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)

    _spawn_bg(_parse_resume_task(resume.id))
    logger.info("简历已入库待解析 id=%s 文本长度=%d", resume.id, len(raw_text))
    return _to_out(resume)


@router.get("/mine", response_model=list[ResumeOut])
async def my_resumes(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        (await db.execute(select(Resume).where(Resume.user_id == user.id).order_by(Resume.id.desc())))
        .scalars()
        .all()
    )
    return [_to_out(r) for r in rows]


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(
    resume_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权删除他人简历")
    file_path = Path(resume.file_path)
    if file_path.exists():
        file_path.unlink()
    if resume.photo_path:
        photo_path = Path(resume.photo_path)
        if photo_path.exists():
            photo_path.unlink()
    await db.delete(resume)
    await db.commit()


async def _get_owned_resume(db: AsyncSession, resume_id: int, user: User) -> Resume:
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问他人简历")
    return resume


@router.post("/{resume_id}/reparse", response_model=ResumeOut)
async def reparse_resume(
    resume_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """解析失败的简历重新触发后台 AI 解析。"""
    resume = await _get_owned_resume(db, resume_id, user)
    if resume.parse_status == ParseStatus.completed:
        raise HTTPException(status_code=400, detail="该简历已完成解析，无需重试")
    # 原子置位：仅 failed 可转 pending；rowcount==0 说明已在解析中或被并发请求抢先
    result = await db.execute(
        update(Resume)
        .where(Resume.id == resume.id, Resume.parse_status == ParseStatus.failed)
        .values(parse_status=ParseStatus.pending)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="该简历正在解析中，请稍候")
    await db.commit()
    _spawn_bg(_parse_resume_task(resume.id))
    await db.refresh(resume)
    return _to_out(resume)


@router.post("/{resume_id}/advice", response_model=ResumeOut)
async def advise_resume_endpoint(
    resume_id: int,
    payload: ResumeAdviceIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """AI 优化建议：只诊断不改写；结果覆盖保存，仅保留最新一轮。"""
    resume = await _get_owned_resume(db, resume_id, user)
    if resume.parse_status != ParseStatus.completed:
        raise HTTPException(status_code=400, detail="该简历尚未完成解析，无法生成建议")
    # LLM 调用耗时较长，放入线程池避免阻塞事件循环
    result = await asyncio.to_thread(
        advise_resume, _build_vector_text(resume), payload.job_requirement
    )
    if not result:
        raise HTTPException(status_code=502, detail="AI 建议生成失败，请稍后重试")
    resume.suggestions = result
    resume.suggestions_at = func.now()
    await db.commit()
    await db.refresh(resume)
    return _to_out(resume)
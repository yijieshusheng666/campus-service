"""AI 简历 API：上传 PDF → 提取文本 → LLM 结构化解析、AI 改良。"""
import io
import logging
from pathlib import Path

import pdfplumber
from PIL import Image
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.core.utils import ALLOWED_PDF_EXT, new_id, safe_filename
from app.database import get_db
from app.models.resume import Resume
from app.models.user import User
from app.schemas.resume import ResumeImproveIn, ResumeImproveOut, ResumeOut, ResumeUpdateIn
from app.services.llm import extract_resume, improve_resume

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resumes", tags=["简历"])


def _ensure_resume_dir() -> Path:
    d = Path(settings.UPLOAD_DIR) / "resumes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _extract_photo_from_pdf(pdf_path: Path, output_dir: Path, base_name: str) -> str | None:
    """从PDF第一页提取头像照片，返回保存的相对路径，失败返回None。"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return None
            page = pdf.pages[0]
            page_width = float(page.width)
            page_height = float(page.height)
            images = page.images
            if not images:
                return None

            best_img = None
            best_area = 0
            for img in images:
                x0 = float(img.get("x0", 0))
                y0 = float(img.get("top", 0) or img.get("y0", 0))
                x1 = float(img.get("x1", 0))
                y1 = float(img.get("bottom", 0) or img.get("y1", 0))
                w = x1 - x0
                h = y1 - y0
                area = w * h
                if area < 2000:
                    continue
                aspect = w / h if h > 0 else 0
                if 0.5 < aspect < 1.8 and area > best_area:
                    is_left_or_top = x0 < page_width * 0.4 or y0 < page_height * 0.3
                    if is_left_or_top or best_img is None:
                        best_area = area
                        best_img = img

            if best_img is None:
                for img in images:
                    x0 = float(img.get("x0", 0))
                    y0 = float(img.get("top", 0) or img.get("y0", 0))
                    x1 = float(img.get("x1", 0))
                    y1 = float(img.get("bottom", 0) or img.get("y1", 0))
                    w = x1 - x0
                    h = y1 - y0
                    area = w * h
                    aspect = w / h if h > 0 else 0
                    if 0.4 < aspect < 2.0 and area > best_area:
                        best_area = area
                        best_img = img

            if best_img is None:
                return None

            stream = best_img.get("stream")
            if stream is None:
                raw_data = best_img.get("data")
                if not raw_data:
                    return None
                if hasattr(raw_data, "get_data"):
                    raw_data = raw_data.get_data()
            else:
                raw_data = stream.get_data()
            if not raw_data:
                return None

            try:
                pil_img = Image.open(io.BytesIO(raw_data))
                if pil_img.mode in ("RGBA", "P"):
                    pil_img = pil_img.convert("RGB")
                photo_filename = f"{base_name}_photo.jpg"
                photo_path = output_dir / photo_filename
                pil_img.save(photo_path, "JPEG", quality=90)
                return str(photo_path)
            except Exception:
                logger.debug("PIL打开图片失败，尝试原始保存", exc_info=True)
                photo_filename = f"{base_name}_photo.png"
                photo_path = output_dir / photo_filename
                photo_path.write_bytes(raw_data)
                return str(photo_path)
    except Exception as e:
        logger.debug("提取PDF照片失败: %s", e)
        return None


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


def _to_out(resume: Resume, include_raw_text: bool = False) -> ResumeOut:
    import os
    out = ResumeOut.model_validate(resume)
    out.raw_text_excerpt = (resume.raw_text or "")[:200]
    if include_raw_text:
        out.raw_text = resume.raw_text or ""
    # 构造PDF文件URL
    if resume.file_path:
        relative_path = os.path.relpath(resume.file_path, settings.UPLOAD_DIR)
        relative_path = relative_path.replace("\\", "/")
        out.pdf_url = f"{settings.STATIC_URL}/{relative_path}"
    # 构造照片URL
    if resume.photo_path:
        photo_rel = os.path.relpath(resume.photo_path, settings.UPLOAD_DIR)
        photo_rel = photo_rel.replace("\\", "/")
        out.photo_url = f"{settings.STATIC_URL}/{photo_rel}"
    return out


@router.post("/upload", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_PDF_EXT:
        raise HTTPException(status_code=400, detail="仅支持 PDF 简历")
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件超过大小限制")

    # 保存本地
    filename = safe_filename(file.filename or "resume.pdf", prefix="resume_")
    file_path = _ensure_resume_dir() / filename
    file_path.write_bytes(content)

    # PDF 文本提取
    try:
        with pdfplumber.open(file_path) as pdf:
            raw_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"PDF 解析失败：{e}") from e

    if not raw_text.strip():
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="未能从 PDF 中提取到文本内容")

    # LLM 结构化提取（失败时保留原文，不影响入库）
    logger.info("开始 LLM 解析简历，文本长度: %d", len(raw_text))
    parsed = extract_resume(raw_text)
    logger.info("LLM 解析结果: %s", {k: (len(v) if isinstance(v, (list, str)) else v) for k, v in parsed.items()})

    # 提取PDF中的照片
    photo_path = None
    try:
        resume_dir = _ensure_resume_dir()
        base_name = Path(filename).stem
        photo_path = _extract_photo_from_pdf(file_path, resume_dir, base_name)
        if photo_path:
            logger.info("已提取简历照片: %s", photo_path)
    except Exception as e:
        logger.debug("照片提取异常: %s", e)

    vector_id = new_id()
    resume = Resume(
        user_id=user.id,
        file_name=file.filename or filename,
        file_path=str(file_path),
        photo_path=photo_path,
        raw_text=raw_text,
        parsed_name=parsed.get("name"),
        parsed_phone=parsed.get("phone"),
        parsed_email=parsed.get("email"),
        parsed_location=parsed.get("location"),
        parsed_job_title=parsed.get("job_title"),
        parsed_education=parsed.get("education") or None,
        parsed_skills=parsed.get("skills") or None,
        parsed_experience=parsed.get("experience") or None,
        parsed_summary=parsed.get("summary"),
        parsed_sections=parsed.get("sections") or None,
        vector_id=vector_id,
    )
    db.add(resume)
    await db.flush()

    await db.commit()
    await db.refresh(resume)
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


@router.get("/{resume_id}", response_model=ResumeOut)
async def get_resume(
    resume_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问他人简历")
    return _to_out(resume, include_raw_text=True)


@router.put("/{resume_id}", response_model=ResumeOut)
async def update_resume(
    resume_id: int,
    payload: ResumeUpdateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新编辑后的简历数据。"""
    resume = await _get_owned_resume(db, resume_id, user)
    resume.edited_data = payload.edited_data
    await db.commit()
    await db.refresh(resume)
    return _to_out(resume)


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


@router.post("/{resume_id}/improve", response_model=ResumeImproveOut)
async def improve_resume_endpoint(
    resume_id: int,
    payload: ResumeImproveIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """AI 改良简历：不传岗位要求则通用优化，传了则定向改良。"""
    resume = await _get_owned_resume(db, resume_id, user)
    result = improve_resume(_build_vector_text(resume), payload.job_requirement)
    if not result:
        raise HTTPException(status_code=502, detail="AI 改良失败，请确认 LLM 服务已启动")
    # 结构化改良数据：供前端以原 PDF 样式预览
    project = {
        "basic": {
            "name": result.get("name", "") or "",
            "title": result.get("job_title", "") or "",
            "phone": result.get("phone", "") or "",
            "email": result.get("email", "") or "",
            "location": result.get("location", "") or "",
            "github": result.get("github", "") or "",
            "links": "",
        },
        "sections": result.get("sections", []),
    }
    return ResumeImproveOut(improved_sections=result.get("sections", []), improved_project=project)
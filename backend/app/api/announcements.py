"""平台公告 API：全员浏览（置顶优先）+ 管理员发布/编辑/下架 + AI 摘要。

AI 摘要策略：发布/修改正文后转后台任务生成（LLM 调用耗时不阻塞接口），
LLM 不可用或失败时回落为「正文前 80 字」——摘要永远不应该是发布公告的前置条件。
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_current_admin, get_current_user
from app.core.dispatch import spawn_bg
from app.database import AsyncSessionLocal, get_db
from app.models.announcement import Announcement
from app.models.user import User
from app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementListItemOut,
    AnnouncementOut,
    AnnouncementUpdate,
)
from app.services.llm import summarize_announcement

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/announcements", tags=["公告"])


async def generate_summary_task(
    announcement_id: int,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> None:
    """后台生成 AI 摘要。session_factory 可注入（测试环境指向测试库）。"""
    try:
        async with session_factory() as db:
            ann = await db.get(Announcement, announcement_id)
            if not ann:
                return
            content = ann.content
        summary = await asyncio.to_thread(summarize_announcement, content)
        if not summary:
            # 回落：LLM 未配置/超时/解析失败时，用正文截断兜底
            summary = " ".join(content.split())[:80]
        async with session_factory() as db:
            ann = await db.get(Announcement, announcement_id)
            if not ann:
                return
            ann.summary = summary
            await db.commit()
        logger.info("公告摘要已生成 id=%s", announcement_id)
    except Exception:
        logger.exception("公告摘要生成失败 id=%s", announcement_id)


# ---------------- 用户端 ----------------

@router.get("")
async def list_announcements(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """公告列表：只展示已上架，置顶在前，其余按发布时间倒序。"""
    base = select(Announcement).where(Announcement.is_online.is_(True))
    total = (
        await db.execute(select(func.count(Announcement.id)).where(Announcement.is_online.is_(True)))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                base.order_by(Announcement.is_pinned.desc(), Announcement.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return {
        "total": total,
        "items": [AnnouncementListItemOut.model_validate(r).model_dump(mode="json") for r in rows],
    }


@router.get("/manage", response_model=list[AnnouncementOut])
async def list_all_for_admin(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """管理端列表：含已下架公告（用户端列表只返回已上架）。

    注意必须声明在 /{announcement_id} 之前，否则 "manage" 会被当成路径参数解析。
    """
    rows = (
        (
            await db.execute(
                select(Announcement)
                .order_by(Announcement.is_pinned.desc(), Announcement.id.desc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    return rows


@router.get("/{announcement_id}", response_model=AnnouncementOut)
async def get_announcement(
    announcement_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    ann = await db.get(Announcement, announcement_id)
    if not ann or not ann.is_online:
        raise HTTPException(status_code=404, detail="公告不存在或已下架")
    return ann


# ---------------- 管理端（同模块内聚，鉴权统一走 get_current_admin） ----------------

@router.post("", response_model=AnnouncementOut, status_code=201)
async def create_announcement(
    payload: AnnouncementCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    ann = Announcement(
        publisher_id=admin.id,
        title=payload.title.strip(),
        content=payload.content.strip(),
        is_pinned=payload.is_pinned,
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    spawn_bg(generate_summary_task(ann.id))
    return ann


@router.put("/{announcement_id}", response_model=AnnouncementOut)
async def update_announcement(
    announcement_id: int,
    payload: AnnouncementUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    ann = await db.get(Announcement, announcement_id)
    if not ann:
        raise HTTPException(status_code=404, detail="公告不存在")
    content_changed = False
    if payload.title is not None:
        ann.title = payload.title.strip()
    if payload.content is not None and payload.content.strip() != ann.content:
        ann.content = payload.content.strip()
        content_changed = True
    if payload.is_pinned is not None:
        ann.is_pinned = payload.is_pinned
    if payload.is_online is not None:
        ann.is_online = payload.is_online
    await db.commit()
    await db.refresh(ann)
    if content_changed:
        spawn_bg(generate_summary_task(ann.id))
    return ann


@router.delete("/{announcement_id}", status_code=204)
async def delete_announcement(
    announcement_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    ann = await db.get(Announcement, announcement_id)
    if not ann:
        raise HTTPException(status_code=404, detail="公告不存在")
    await db.delete(ann)
    await db.commit()


@router.post("/{announcement_id}/summary")
async def regenerate_summary(
    announcement_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """手动重新生成 AI 摘要（异步，前端稍后刷新即可看到）。"""
    ann = await db.get(Announcement, announcement_id)
    if not ann:
        raise HTTPException(status_code=404, detail="公告不存在")
    spawn_bg(generate_summary_task(ann.id))
    return {"detail": "摘要生成中，请稍后刷新查看"}

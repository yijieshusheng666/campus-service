"""平台公告 API：全员浏览（置顶优先）+ 管理员发布/编辑/下架。"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.database import get_db
from app.models.announcement import Announcement
from app.models.user import User
from app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementListItemOut,
    AnnouncementOut,
    AnnouncementUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/announcements", tags=["公告"])


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
    if payload.title is not None:
        ann.title = payload.title.strip()
    if payload.content is not None:
        ann.content = payload.content.strip()
    if payload.is_pinned is not None:
        ann.is_pinned = payload.is_pinned
    if payload.is_online is not None:
        ann.is_online = payload.is_online
    await db.commit()
    await db.refresh(ann)
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

"""私信 REST API：会话列表聚合、历史消息游标分页、标记已读。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.message import Message
from app.models.user import User
from app.schemas.message import ConversationOut, MessageOut

router = APIRouter(prefix="/messages", tags=["私信"])


# ---- 会话列表：最近联系人 + 最后一条消息 + 未读数 ----
# 注意：本路由必须先于 /{user_id} 注册，否则 "conversations" 会被当作路径参数解析
@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    me = user.id
    # 对方 id = CASE WHEN 我是发送方 THEN 接收方 ELSE 发送方
    other = case((Message.sender_id == me, Message.receiver_id), else_=Message.sender_id)
    sub = (
        select(
            other.label("other_id"),
            func.max(Message.id).label("last_id"),
            # 未读 = 对方发给我且未读的消息数
            func.sum(
                case((and_(Message.sender_id != me, Message.is_read.is_(False)), 1), else_=0)
            ).label("unread"),
        )
        .where(or_(Message.sender_id == me, Message.receiver_id == me))
        .group_by(other)
        .subquery()
    )
    stmt = (
        select(Message, User, sub.c.unread)
        .select_from(Message)
        .join(sub, Message.id == sub.c.last_id)
        .join(User, User.id == sub.c.other_id)
        .order_by(Message.id.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        ConversationOut(
            user_id=u.id,
            username=u.username,
            nickname=u.nickname,
            last_message=m.content,
            last_time=m.created_at,
            unread=int(unread or 0),
        )
        for m, u, unread in rows
    ]


# ---- 与某人的历史消息（游标分页，返回按时间正序）----
@router.get("/{user_id}", response_model=list[MessageOut])
async def list_messages(
    user_id: int,
    before_id: int | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if await db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    me = user.id
    stmt = (
        select(Message)
        .where(
            or_(
                and_(Message.sender_id == me, Message.receiver_id == user_id),
                and_(Message.sender_id == user_id, Message.receiver_id == me),
            )
        )
        .order_by(Message.id.desc())
        .limit(min(max(limit, 1), 100))
    )
    if before_id is not None:
        stmt = stmt.where(Message.id < before_id)
    messages = list((await db.execute(stmt)).scalars().all())
    messages.reverse()  # 倒序取最新一页，返回时转为正序便于前端渲染
    return messages


# ---- 标记对方发来的消息为已读 ----
@router.put("/{user_id}/read")
async def mark_read(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        update(Message)
        .where(
            Message.sender_id == user_id,
            Message.receiver_id == user.id,
            Message.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await db.commit()
    return {"ok": True, "read": result.rowcount}

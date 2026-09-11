"""管理后台接口。

鉴权策略：所有接口统一挂在 /api/v1/admin 前缀下，并统一依赖 get_current_admin。
鉴权只写一次，新增接口时不可能漏掉——比在每个函数体里手动判 is_admin 可靠。

刻意【不】提供「把某用户设为管理员」的接口：管理员互相提权是最经典的一类
权限漏洞。要新增管理员，直接在服务器上跑 scripts/create_admin.py，
让这个动作必须有人登录服务器才能完成。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin
from app.core.utils import escape_like
from app.database import get_db
from app.models.errand import Errand, ErrandStatus
from app.models.goods import Goods, GoodsStatus
from app.models.interview import MockInterview
from app.models.message import Message
from app.models.order import Order, OrderStatus
from app.models.resume import Resume
from app.models.user import User
from app.schemas.admin import (
    AdminGoodsStatusIn,
    AdminStatsOut,
    AdminUserOut,
    AdminUserStatusIn,
)
from app.schemas.errand import ErrandOut
from app.schemas.goods import GoodsOut
from app.schemas.message import MessageOut
from app.schemas.order import OrderOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["管理后台"])

# 列表接口的上限。数据量大了以后要换成真正的游标分页，现在这个量级没必要。
MAX_LIMIT = 500


async def _count(db: AsyncSession, model, *where) -> int:
    """统计行数。计数交给数据库做，传输量恒定，也不随数据量增长变慢。"""
    stmt = select(func.count()).select_from(model)
    if where:
        stmt = stmt.where(*where)
    return int((await db.execute(stmt)).scalar_one())


# ---------------- 总览 ----------------


@router.get("/stats", response_model=AdminStatsOut, summary="数据总览")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    return AdminStatsOut(
        users=await _count(db, User),
        admins=await _count(db, User, User.is_admin.is_(True)),
        users_active=await _count(db, User, User.is_active.is_(True)),
        goods=await _count(db, Goods),
        goods_on_sale=await _count(db, Goods, Goods.status == GoodsStatus.on_sale),
        goods_off_shelf=await _count(db, Goods, Goods.status == GoodsStatus.off_shelf),
        orders=await _count(db, Order),
        orders_completed=await _count(db, Order, Order.status == OrderStatus.completed),
        errands=await _count(db, Errand),
        errands_pending=await _count(db, Errand, Errand.status == ErrandStatus.pending),
        messages=await _count(db, Message),
        resumes=await _count(db, Resume),
        interviews=await _count(db, MockInterview),
    )


# ---------------- 用户 ----------------


@router.get("/users", response_model=list[AdminUserOut], summary="用户列表")
async def list_users(
    keyword: str | None = Query(default=None, description="按用户名 / 邮箱模糊匹配"),
    limit: int = Query(default=200, ge=1, le=MAX_LIMIT),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    stmt = select(User).order_by(User.id.desc()).limit(limit)
    if keyword and keyword.strip():
        # escape_like 把用户输入里的 % 和 _ 转义掉，
        # 否则搜 "a%b" 会变成通配查询，既不准也可能被用来做大范围扫描
        kw = f"%{escape_like(keyword.strip())}%"
        stmt = stmt.where(or_(User.username.like(kw), User.email.like(kw)))
    return list((await db.execute(stmt)).scalars().all())


@router.put("/users/{user_id}/status", response_model=AdminUserOut, summary="封禁 / 解封用户")
async def set_user_active(
    user_id: int,
    payload: AdminUserStatusIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 两条护栏：封禁自己会把自己锁在门外；封禁别的管理员等于用管理权限
    # 去削弱管理权限本身。这两件事都不该允许，哪怕是自己操作也不行。
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="不能封禁自己的账号")
    if user.is_admin and not payload.is_active:
        raise HTTPException(status_code=400, detail="不能封禁管理员账号")

    user.is_active = payload.is_active
    await db.commit()
    await db.refresh(user)
    logger.info("管理员 %s 将用户 %s 设为 is_active=%s", admin.id, user.id, payload.is_active)
    return user


# ---------------- 商品 ----------------


@router.get("/goods", response_model=list[GoodsOut], summary="全部商品")
async def list_goods(
    status: GoodsStatus | None = Query(default=None, description="按状态筛选"),
    limit: int = Query(default=200, ge=1, le=MAX_LIMIT),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    # seller 是 lazy="joined"，会自动带出来；images 需要显式 selectinload，
    # 否则序列化时触发懒加载 → 在异步会话里直接报 MissingGreenlet
    stmt = (
        select(Goods)
        .options(selectinload(Goods.images))
        .order_by(Goods.id.desc())
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(Goods.status == status)
    return list((await db.execute(stmt)).scalars().all())


@router.put("/goods/{goods_id}/status", response_model=GoodsOut, summary="下架 / 恢复商品")
async def set_goods_status(
    goods_id: int,
    payload: AdminGoodsStatusIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    goods = (
        await db.execute(
            select(Goods).options(selectinload(Goods.images)).where(Goods.id == goods_id)
        )
    ).scalar_one_or_none()
    if not goods:
        raise HTTPException(status_code=404, detail="商品不存在")

    goods.status = payload.status
    await db.commit()
    await db.refresh(goods)
    logger.info("管理员 %s 将商品 %s 状态改为 %s", admin.id, goods_id, payload.status.value)
    return goods


@router.delete("/goods/{goods_id}", summary="删除商品")
async def delete_goods(
    goods_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    goods = await db.get(Goods, goods_id)
    if not goods:
        raise HTTPException(status_code=404, detail="商品不存在")

    # orders.goods_id 上的外键是 ondelete=CASCADE —— 直接删商品会连带把订单
    # 一起删掉，而且是静默的。这对「管理数据」来说太危险了：订单是交易记录，
    # 不该因为删了个商品就凭空消失。所以有订单时拒绝删除，引导去下架。
    order_count = await _count(db, Order, Order.goods_id == goods_id)
    if order_count:
        raise HTTPException(
            status_code=400,
            detail=f"该商品已有 {order_count} 笔订单，删除会连带删掉订单记录。请改用「下架」。",
        )

    await db.delete(goods)  # images 由 relationship 的 delete-orphan 一并清理
    await db.commit()
    logger.info("管理员 %s 删除了商品 %s", admin.id, goods_id)
    return {"message": "商品已删除"}


# ---------------- 订单 ----------------


@router.get("/orders", response_model=list[OrderOut], summary="全部订单")
async def list_orders(
    limit: int = Query(default=200, ge=1, le=MAX_LIMIT),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    # buyer / seller / goods 都是 lazy="joined"，不需要额外 options
    stmt = select(Order).order_by(Order.id.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


# ---------------- 校园跑腿 ----------------


@router.get("/errands", response_model=list[ErrandOut], summary="全部跑腿需求")
async def list_errands(
    limit: int = Query(default=200, ge=1, le=MAX_LIMIT),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    stmt = (
        select(Errand)
        .options(selectinload(Errand.publisher), selectinload(Errand.runner))
        .order_by(Errand.id.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


@router.delete("/errands/{errand_id}", summary="删除跑腿需求")
async def delete_errand(
    errand_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    errand = await db.get(Errand, errand_id)
    if not errand:
        raise HTTPException(status_code=404, detail="跑腿需求不存在")
    await db.delete(errand)
    await db.commit()
    logger.info("管理员 %s 删除了跑腿需求 %s", admin.id, errand_id)
    return {"message": "跑腿需求已删除"}


# ---------------- 站内私信 ----------------


@router.get("/messages", response_model=list[MessageOut], summary="站内私信记录")
async def list_messages(
    limit: int = Query(default=200, ge=1, le=MAX_LIMIT),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """只读。私信是双方对话，管理员删除单条会破坏会话完整性，
    需要处置时用「封禁用户」而不是「删消息」。"""
    stmt = select(Message).order_by(Message.id.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())

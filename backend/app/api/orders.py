"""订单 API：下单、我的订单列表、状态更新（付款/发货/确认收货/取消）。"""
import time
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.goods import Goods, GoodsStatus
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.schemas.order import OrderCreate, OrderOut, OrderStatusUpdate

router = APIRouter(prefix="/orders", tags=["订单"])


def _gen_order_no() -> str:
    return str(int(time.time() * 1000))


async def _load_order(db: AsyncSession, order_id: int) -> Order:
    order = (
        await db.execute(
            select(Order)
            .options(selectinload(Order.buyer), selectinload(Order.seller), selectinload(Order.goods).selectinload(Goods.images))
            .where(Order.id == order_id)
        )
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order


def _serialize(order: Order) -> dict:
    cover = ""
    if order.goods and order.goods.images:
        cover = order.goods.images[0].url
    return {
        "id": order.id,
        "order_no": order.order_no,
        "buyer_id": order.buyer_id,
        "seller_id": order.seller_id,
        "goods_id": order.goods_id,
        "price": order.price,
        "status": order.status,
        "contact": order.contact,
        "remark": order.remark,
        "created_at": order.created_at,
        "buyer": {"id": order.buyer.id, "username": order.buyer.username, "nickname": getattr(order.buyer, "nickname", None)} if order.buyer else None,
        "seller": {"id": order.seller.id, "username": order.seller.username, "nickname": getattr(order.seller, "nickname", None)} if order.seller else None,
        "goods_title": order.goods.title if order.goods else "",
        "goods_cover": cover,
        "goods": {
            "id": order.goods.id,
            "title": order.goods.title,
            "price": order.goods.price,
            "cover": cover
        } if order.goods else None,
    }


# ---- 下单 ----
@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 加载商品
    goods = (
        await db.execute(
            select(Goods).where(Goods.id == payload.goods_id)
        )
    ).scalar_one_or_none()
    if not goods:
        raise HTTPException(status_code=404, detail="商品不存在")
    if goods.status != GoodsStatus.on_sale:
        raise HTTPException(status_code=400, detail="该商品已下架或售出")
    if goods.seller_id == user.id:
        raise HTTPException(status_code=400, detail="不能购买自己的商品")

    order = Order(
        order_no=_gen_order_no(),
        buyer_id=user.id,
        seller_id=goods.seller_id,
        goods_id=goods.id,
        price=goods.price,
        status=OrderStatus.pending,
        contact=payload.contact or user.username,
        remark=payload.remark,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return _serialize(await _load_order(db, order.id))


# ---- 我的订单（分买家/卖家视角，通过 role 参数区分）----
@router.get("", response_model=list[OrderOut])
async def list_orders(
    role: str = "buyer",  # buyer / seller
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if role == "seller":
        stmt = (
            select(Order)
            .options(selectinload(Order.buyer), selectinload(Order.seller), selectinload(Order.goods).selectinload(Goods.images))
            .where(Order.seller_id == user.id)
            .order_by(Order.id.desc())
        )
    else:
        stmt = (
            select(Order)
            .options(selectinload(Order.buyer), selectinload(Order.seller), selectinload(Order.goods).selectinload(Goods.images))
            .where(Order.buyer_id == user.id)
            .order_by(Order.id.desc())
        )
    items = list((await db.execute(stmt)).scalars().all())
    return [_serialize(o) for o in items]


# ---- 订单详情 ----
@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = await _load_order(db, order_id)
    if order.buyer_id != user.id and order.seller_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看该订单")
    return _serialize(order)


# ---- 更新订单状态（买家/卖家分别可操作对应状态）----
@router.put("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = await _load_order(db, order_id)
    new_status = payload.status

    # 状态流转校验
    if new_status == OrderStatus.paid:
        # 买家付款（pending -> paid）
        if order.buyer_id != user.id:
            raise HTTPException(status_code=403, detail="只有买家可以付款")
        if order.status != OrderStatus.pending:
            raise HTTPException(status_code=400, detail="当前状态不可付款")
        # 付款后立即下架商品，防止同一件商品被再次购买
        goods = (await db.execute(select(Goods).where(Goods.id == order.goods_id))).scalar_one_or_none()
        if goods and goods.status == GoodsStatus.on_sale:
            goods.status = GoodsStatus.sold
    elif new_status == OrderStatus.shipped:
        # 卖家发货（paid -> shipped）
        if order.seller_id != user.id:
            raise HTTPException(status_code=403, detail="只有卖家可以发货")
        if order.status != OrderStatus.paid:
            raise HTTPException(status_code=400, detail="当前状态不可发货")
    elif new_status == OrderStatus.completed:
        # 买家确认收货（shipped -> completed），同时把商品标记为已售
        if order.buyer_id != user.id:
            raise HTTPException(status_code=403, detail="只有买家可以确认收货")
        if order.status != OrderStatus.shipped:
            raise HTTPException(status_code=400, detail="当前状态不可确认收货")
        # 商品标记已售
        goods = (await db.execute(select(Goods).where(Goods.id == order.goods_id))).scalar_one_or_none()
        if goods:
            goods.status = GoodsStatus.sold
    elif new_status == OrderStatus.cancelled:
        # 取消订单：pending 状态买卖双方均可取消
        if order.buyer_id != user.id and order.seller_id != user.id:
            raise HTTPException(status_code=403, detail="无权取消该订单")
        if order.status not in (OrderStatus.pending, OrderStatus.paid):
            raise HTTPException(status_code=400, detail="当前状态不可取消")
    else:
        raise HTTPException(status_code=400, detail="不支持的状态")

    order.status = new_status
    await db.commit()
    return _serialize(await _load_order(db, order.id))

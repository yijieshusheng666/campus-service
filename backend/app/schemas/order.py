"""订单契约。"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.order import OrderStatus


class OrderGoodsOut(BaseModel):
    id: int
    title: str
    price: Decimal
    cover: str = ""

    model_config = ConfigDict(from_attributes=True)


class OrderUserOut(BaseModel):
    id: int
    username: str
    nickname: str | None = None

    model_config = ConfigDict(from_attributes=True)


class OrderCreate(BaseModel):
    goods_id: int
    contact: str | None = None
    remark: str | None = None


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str
    buyer_id: int
    seller_id: int
    goods_id: int
    price: Decimal
    status: OrderStatus
    contact: str | None
    remark: str | None
    created_at: datetime

    buyer: OrderUserOut | None = None
    seller: OrderUserOut | None = None
    goods_title: str = ""
    goods_cover: str = ""
    goods: OrderGoodsOut | None = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus

"""私信契约。"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class GoodsBriefOut(BaseModel):
    """商品卡片摘要：只带渲染气泡所需的 4 个字段，不带描述/卖家等冗余信息。

    cover 来自 Goods.cover 属性（首图），因此查消息时必须
    joinedload(Message.goods).selectinload(Goods.images) 预加载，否则异步上下文会抛
    MissingGreenlet（懒加载在 async 下不可用）。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    price: Decimal
    status: str
    cover: str | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_id: int
    receiver_id: int
    content: str
    goods_id: int | None = None
    goods: GoodsBriefOut | None = None
    is_read: bool
    created_at: datetime


class ConversationOut(BaseModel):
    """会话列表项：对方信息 + 最后一条消息 + 未读数。"""

    user_id: int
    username: str
    nickname: str | None = None
    last_message: str
    last_time: datetime
    unread: int

"""私信契约。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_id: int
    receiver_id: int
    content: str
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

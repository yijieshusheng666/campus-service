"""私信模型：用户间一对一消息，落库优先、离线可补拉。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    receiver_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    sender: Mapped["User"] = relationship(foreign_keys=[sender_id], lazy="joined")
    receiver: Mapped["User"] = relationship(foreign_keys=[receiver_id], lazy="joined")

    # 复合索引：会话查询（双方消息按 id 倒序）与未读统计的核心路径
    __table_args__ = (
        Index("ix_messages_sender_receiver_id", "sender_id", "receiver_id", "id"),
    )

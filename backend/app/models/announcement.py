"""平台公告模型：管理员发布 → 全员可见，支持置顶与 AI 摘要。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    publisher_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # AI 生成的一句话摘要（列表页展示）；LLM 不可用时回落为正文前 80 字
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # 下架不删数据：公告有审计价值（"当时通知过什么"），下线只是对用户不可见
    is_online: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    publisher: Mapped["User"] = relationship(foreign_keys=[publisher_id], lazy="joined")

"""快递代拿模型：发布需求 → 接单 → 送达 → 结算。"""
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ErrandStatus(str, enum.Enum):
    pending = "pending"      # 待接单
    accepted = "accepted"    # 已接单配送中
    delivered = "delivered"  # 已送达待确认
    completed = "completed"  # 已结算
    cancelled = "cancelled"  # 已取消


class Errand(Base):
    __tablename__ = "errands"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    runner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pickup_location: Mapped[str] = mapped_column(String(200), nullable=False)
    package_info: Mapped[str] = mapped_column(String(200), nullable=False)
    dropoff_location: Mapped[str] = mapped_column(String(200), nullable=False)
    reward: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[ErrandStatus] = mapped_column(
        Enum(ErrandStatus), default=ErrandStatus.pending, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    publisher: Mapped["User"] = relationship(foreign_keys=[user_id], lazy="joined")
    runner: Mapped["User | None"] = relationship(foreign_keys=[runner_id], lazy="joined")

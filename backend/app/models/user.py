"""用户模型：登录注册用户统一身份，均可买卖二手与使用求职功能。"""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True)
    # 平台管理员：可访问 /api/v1/admin/* 下的全部接口。
    # 刻意不做成 role 枚举或独立角色表——这个平台只需要「普通用户 / 管理员」两档，
    # 多一层抽象等于为不存在的需求付复杂度。真出现第三种角色时再抽也不迟。
    is_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    goods: Mapped[list["Goods"]] = relationship(back_populates="seller")
    favorites: Mapped[list["Favorite"]] = relationship(back_populates="user")
    resumes: Mapped[list["Resume"]] = relationship(back_populates="user")
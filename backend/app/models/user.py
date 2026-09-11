"""用户模型：登录注册用户统一身份，均可买卖二手与使用求职功能。"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
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


class RefreshToken(Base):
    """刷新令牌登记表：JWT 本身无状态、签出即收不回，吊销能力全靠这张表。

    设计要点：
    - refresh token 的 JWT payload 里带唯一 jti，这里只记 jti 的存废；
      校验时先验签（没被伪造）再查表（没被吊销），两层缺一不可
    - 登出 / 轮换 / 管理员封禁 = 把对应行的 revoked 置 True
    - 轮换时旧 jti 置 revoked 后保留（而非删除）：再次出现即「重放攻击」信号，
      据此可吊销该用户全部令牌
    """
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    jti: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
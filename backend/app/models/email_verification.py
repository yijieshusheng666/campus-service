"""邮箱验证码：用于注册时证明「这个邮箱确实归你所有」。

设计要点：
- **只存哈希**：库被拖走也拿不到可用验证码（6 位纯数字明文等于没有防护）。
  哈希用 sha256(email + code + SECRET_KEY)，加 SECRET_KEY 是防止彩虹表批量比对。
- **带 purpose**：注册 / 找回密码共用一张表，校验时按用途隔离，
  注册的码不能拿去重置密码（否则拿注册验证码就能改别人密码）。
- **attempts 计数**：错误次数超限即作废，否则 6 位数字可以在一小时内被暴力枚举完。
- **保留历史行不删**：便于做「每小时发送次数」限流统计与事后审计。
"""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EmailVerification(Base):
    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)  # register | reset
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 限流统计按「邮箱 + 用途 + 时间」查，这个复合索引就是它的路径
    __table_args__ = (
        Index("ix_email_verifications_email_purpose_created", "email", "purpose", "created_at"),
    )

"""邮箱验证码：用于注册时证明「这个邮箱确实归你所有」。

设计要点：
- **只存哈希**：库被拖走也拿不到可用验证码（6 位纯数字明文等于没有防护）。
  哈希用 sha256(email + code + SECRET_KEY)，加 SECRET_KEY 是防止彩虹表批量比对。
- **带 purpose**：注册 / 找回密码共用一张表，校验时按用途隔离，
  注册的码不能拿去重置密码（否则拿注册验证码就能改别人密码）。
- **attempts 计数**：错误次数超限即作废，否则 6 位数字可以在一小时内被暴力枚举完。
- **保留历史行不删**：便于做「每小时发送次数」限流统计与事后审计。
- **时间一律由应用侧写入（见下方 created_at 注释）**：这是踩过线上事故后加上的约束。
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    """naive UTC —— 与 services/email_code._now() 同一口径（MySQL 的 DateTime 无时区）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EmailVerification(Base):
    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)  # register | reset
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ⚠️ created_at 必须由应用侧写入（default=_utcnow），不能只依赖 MySQL 的 NOW()：
    # 本表的所有时间比较（60 秒冷却、每小时次数）都用 Python 的 UTC，
    # 而 MySQL 的 NOW() 返回的是**会话时区**的时间（阿里云服务器上是 UTC+8），
    # 两者相差 8 小时 → 冷却计算得出负的 elapsed → 报「请 25561 秒后再试」（约 7 小时）。
    # 之所以本地测试发现不了：SQLite 的 CURRENT_TIMESTAMP 恰好是 UTC，完全一致。
    # server_default 保留只为「非 ORM 写入（如手工 SQL / 数据修复）」兜底。
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, server_default=func.now()
    )

    # 限流统计按「邮箱 + 用途 + 时间」查，这个复合索引就是它的路径
    __table_args__ = (
        Index("ix_email_verifications_email_purpose_created", "email", "purpose", "created_at"),
    )

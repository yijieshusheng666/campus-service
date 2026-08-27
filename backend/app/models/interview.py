"""AI 模拟面试模型：会话 + 多轮消息。"""
import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InterviewStatus(str, enum.Enum):
    ongoing = "ongoing"      # 进行中
    completed = "completed"  # 已结束（含评估报告）


class MockInterview(Base):
    __tablename__ = "mock_interviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True
    )
    job_position: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[InterviewStatus] = mapped_column(
        Enum(InterviewStatus), default=InterviewStatus.ongoing, index=True
    )
    # 评估报告 JSON：overall_score / dimensions / strengths / weaknesses / suggestions
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    messages: Mapped[list["InterviewMessage"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan", order_by="InterviewMessage.id"
    )


class InterviewMessage(Base):
    __tablename__ = "interview_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("mock_interviews.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # assistant | user
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    interview: Mapped["MockInterview"] = relationship(back_populates="messages")

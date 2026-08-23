"""简历模型：存储原始文本、LLM 结构化提取结果与向量化状态。"""
import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ParseStatus(str, enum.Enum):
    pending = "pending"          # 待后台解析
    completed = "completed"      # 解析完成
    failed = "failed"            # 解析失败（可重试）


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    raw_text: Mapped[str] = mapped_column(Text, default="")

    # LLM 结构化提取结果
    parsed_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parsed_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    parsed_email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parsed_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parsed_job_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parsed_education: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    parsed_skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    parsed_experience: Mapped[list | None] = mapped_column(JSON, nullable=True)
    parsed_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 动态模块结构（解析后的全部模块，前端据此自由识别渲染）
    parsed_sections: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # 用户编辑后的简历数据（在线编辑器使用）
    edited_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    parse_status: Mapped[ParseStatus] = mapped_column(
        Enum(ParseStatus), default=ParseStatus.completed, server_default="completed"
    )

    is_vectorized: Mapped[bool] = mapped_column(default=False)
    vector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # ChromaDB id

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="resumes")
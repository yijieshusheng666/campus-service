"""AI 模拟面试契约。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.interview import InterviewStatus


class InterviewCreate(BaseModel):
    resume_id: int | None = None
    job_position: str = Field(min_length=1, max_length=100)


class InterviewMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class InterviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resume_id: int | None
    job_position: str
    status: InterviewStatus
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_content: str = ""


class InterviewDetailOut(InterviewOut):
    messages: list[InterviewMessageOut] = []
    report: dict | None = None


class InterviewChatIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)

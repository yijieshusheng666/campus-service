"""简历契约。"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    parse_status: str = "completed"
    created_at: datetime
    pdf_url: str = ""
    parsed_name: str | None = None
    parsed_job_title: str | None = None
    suggestions: dict[str, Any] | None = None
    suggestions_at: datetime | None = None


class ResumeAdviceIn(BaseModel):
    """AI 优化建议请求：可携带岗位要求做定向诊断。"""
    job_requirement: str | None = None

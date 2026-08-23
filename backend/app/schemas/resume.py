"""简历契约。"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ResumeParseIn(BaseModel):
    """用于『仅让 LLM 重算已有文本』的可选请求。"""
    raw_text: str | None = None


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    parse_status: str = "completed"
    created_at: datetime
    raw_text_excerpt: str = ""
    is_vectorized: bool = False
    pdf_url: str = ""
    photo_url: str = ""
    parsed_name: str | None = None
    parsed_phone: str | None = None
    parsed_email: str | None = None
    parsed_location: str | None = None
    parsed_job_title: str | None = None
    parsed_education: list | dict | None = None
    parsed_skills: list | None = None
    parsed_experience: list | None = None
    parsed_summary: str | None = None
    parsed_sections: list | None = None
    raw_text: str = ""
    edited_data: dict[str, Any] | None = None


class ResumeUpdateIn(BaseModel):
    """更新编辑后的简历数据。"""
    edited_data: dict[str, Any]


class ResumeImproveIn(BaseModel):
    """AI 改良简历请求：可携带岗位要求做定向改良。"""
    job_requirement: str | None = None


class ResumeImproveOut(BaseModel):
    improved_text: str = ""
    improved_sections: list | None = None
    improved_project: dict[str, Any] | None = None
    change_log: list | None = None
"""用户资料契约。"""
from datetime import datetime

from pydantic import BaseModel


class UserProfileOut(BaseModel):
    id: int
    username: str
    email: str
    nickname: str | None = None
    avatar: str | None = None
    phone: str | None = None
    has_parsed_resume: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}
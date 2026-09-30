"""平台公告契约。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AnnouncementPublisherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nickname: str | None = None


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)
    is_pinned: bool = False


class AnnouncementUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=10000)
    is_pinned: bool | None = None
    is_online: bool | None = None


class AnnouncementListItemOut(BaseModel):
    """列表项：不带正文（列表页只展示摘要，正文详情页再拉）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: str | None
    is_pinned: bool
    created_at: datetime
    publisher: AnnouncementPublisherOut | None = None


class AnnouncementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    summary: str | None
    is_pinned: bool
    is_online: bool
    created_at: datetime
    updated_at: datetime
    publisher: AnnouncementPublisherOut | None = None

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
    # 必须带上 is_admin：前端刷新页面时会调 /auth/me 重新拉当前用户，
    # 如果这个契约里没有它，管理员标记就会在刷新后丢掉，
    # 表现为「管理后台菜单一闪就没了、直接访问 /admin 被踢回首页」。
    is_admin: bool = False
    has_parsed_resume: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}
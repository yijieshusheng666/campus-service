"""认证契约。"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=120, description="用户名或邮箱")
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    nickname: str | None = None
    phone: str | None = None
    avatar: str | None = None
    # 前端靠这个字段决定侧边栏是否显示「管理后台」入口，
    # 以及路由守卫是否放行 /admin。注意它只是 UI 层的便利，
    # 真正的权限边界在后端 get_current_admin，前端藏起来不算保护。
    is_admin: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshIn(BaseModel):
    refresh_token: str
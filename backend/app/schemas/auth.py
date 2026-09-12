"""认证契约。"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    # 仅当 REQUIRE_EMAIL_VERIFY=True 时必填（见 api/auth.py）。默认不要求，
    # 这样 SMTP 还没配好的部署不会因为改契约而注册不了。
    email_code: str | None = Field(default=None, max_length=10)


class SendEmailCodeIn(BaseModel):
    email: EmailStr
    purpose: str = Field(default="register", pattern="^(register)$")


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


class RegisterPolicyOut(BaseModel):
    """注册策略：前端据此决定是否显示/要求「邮箱验证码」输入框。

    不把开关硬编码在前端 —— 后端一改配置，前端就跟着变，避免两边不一致。
    """

    require_email_verify: bool
    email_configured: bool  # SMTP 是否已配置；未配置时前端给出友好提示
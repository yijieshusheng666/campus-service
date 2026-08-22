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
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
"""Pydantic V2 模式包（API 请求/响应契约）。"""
from app.schemas.auth import (LoginIn, RegisterIn, TokenOut, UserOut)
from app.schemas.goods import (GoodsCreate, GoodsImageOut, GoodsOut, GoodsUpdate)
from app.schemas.resume import (ResumeImproveIn, ResumeImproveOut, ResumeOut, ResumeParseIn, ResumeUpdateIn)
from app.schemas.user import UserProfileOut

__all__ = [
    "LoginIn", "RegisterIn", "TokenOut", "UserOut",
    "UserProfileOut",
    "GoodsCreate", "GoodsImageOut", "GoodsOut", "GoodsUpdate",
    "ResumeOut", "ResumeParseIn", "ResumeUpdateIn", "ResumeImproveIn", "ResumeImproveOut",
]
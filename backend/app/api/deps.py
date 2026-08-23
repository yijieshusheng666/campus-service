"""FastAPI 依赖：认证。

- 依赖注入当前用户（从 Bearer token 解析 JWT）。
- get_optional_user 用于未登录也可浏览的接口。
"""
import logging

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证令牌")
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或过期的令牌") from e
    user_id = int(payload.get("sub"))
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被禁用")
    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """可选认证：无令牌或令牌无效返回 None；仅吞掉认证类异常，数据库错误正常抛出。"""
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        user_id = int(payload.get("sub"))
    except (jwt.PyJWTError, ValueError, TypeError):
        return None
    return await db.get(User, user_id)
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
    if payload.get("type") == "refresh":
        # refresh token 只允许出现在 /auth/refresh，拿它访问业务接口一律拒绝——
        # 它的生命周期长得多，若能当 access 用，「短命 access」就白设计了
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或过期的令牌")
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
        if payload.get("type") == "refresh":
            return None
        user_id = int(payload.get("sub"))
    except (jwt.PyJWTError, ValueError, TypeError):
        return None
    return await db.get(User, user_id)


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """管理员依赖：在已认证的基础上再校验 is_admin。

    刻意包在 get_current_user 之上，而不是把 is_admin 判断塞进 get_current_user：
    这样「未登录」返回 401、「已登录但不是管理员」返回 403，两者语义分开，
    前端可以据此区分「跳去登录」和「提示无权限」——混成一个 401 就分不清了。

    所有 /api/v1/admin/* 接口统一依赖它，不需要在每个函数体里重复判 is_admin。
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限"
        )
    return current_user
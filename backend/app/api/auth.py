"""认证 API：注册、登录、刷新令牌、登出、获取个人信息。

双令牌体系：
- access  15 分钟，无状态，访问业务接口用
- refresh 7 天，jti 登记在 refresh_tokens 表，只有它能换新令牌对
- 登出/封禁 = 吊销 refresh（表里 revoked=True）；access 等它自然过期（≤15 分钟）
- 轮换：每次 refresh 都换发新的 refresh 并吊销旧的；
  「已吊销的 refresh 再次出现」= 重放攻击信号，吊销该用户全部 refresh
"""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.resume import Resume
from app.models.user import RefreshToken, User
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenOut, UserOut
from app.schemas.user import UserProfileOut

import jwt

router = APIRouter(prefix="/auth", tags=["认证"])


async def _issue_token_pair(user: User, db: AsyncSession) -> TokenOut:
    """签发 access + refresh，并把 refresh 的 jti 登记入库。

    expires_at 存 naive UTC（MySQL DateTime 无时区），比较时统一转回 aware UTC。
    """
    access = create_access_token(subject=str(user.id))
    refresh, jti = create_refresh_token(subject=str(user.id))
    db.add(RefreshToken(
        jti=jti,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await db.commit()
    return TokenOut(access_token=access, refresh_token=refresh, user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterIn, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(User).where((User.email == payload.email) | (User.username == payload.username))
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="邮箱或用户名已被占用")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return await _issue_token_pair(user, db)


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)):
    identifier = payload.identifier.strip()
    # 含 @ 视为邮箱，否则视为用户名
    field = User.email if "@" in identifier else User.username
    user = (
        await db.execute(select(User).where(field == identifier))
    ).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    return await _issue_token_pair(user, db)


@router.post("/refresh", response_model=TokenOut)
async def refresh(payload: RefreshIn, db: AsyncSession = Depends(get_db)):
    """用 refresh token 换一对新令牌（轮换：旧的立即作废）。

    三种拒绝场景，语义不同但对外统一 401，避免向攻击者透露细节：
    1. 签名/过期 —— 伪造或超期
    2. jti 不存在 —— 伪造签名（连登记都没有）
    3. jti 已吊销 —— 两种可能：正常登出后复用，或「重放攻击」（旧令牌被偷后
       与新持有者同时使用）。无法区分，按更坏的情况处理：吊销该用户全部 refresh，
       强制所有端重新登录。
    """
    try:
        decoded = decode_token(payload.refresh_token)
        if decoded.get("type") != "refresh":
            raise jwt.PyJWTError("not a refresh token")
        jti, user_id = decoded["jti"], int(decoded["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")

    row = (
        await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")

    if row.revoked:
        # 重放检测：吊销过的令牌再次出现，全部吊销
        await db.execute(
            update(RefreshToken).where(RefreshToken.user_id == row.user_id).values(revoked=True)
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")

    if row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被禁用")

    row.revoked = True  # 轮换：旧 refresh 立即作废
    return await _issue_token_pair(user, db)


@router.post("/logout")
async def logout(payload: RefreshIn, db: AsyncSession = Depends(get_db)):
    """登出：吊销提交的 refresh token。

    不要求 access 鉴权——refresh token 本身就是凭证，它泄露的场景下
    攻击者同样持有 access，校验 access 防不住任何东西。
    """
    try:
        decoded = decode_token(payload.refresh_token)
        jti = decoded.get("jti")
    except jwt.PyJWTError:
        jti = None
    if jti:
        await db.execute(
            update(RefreshToken).where(RefreshToken.jti == jti).values(revoked=True)
        )
        await db.commit()
    return {"status": "ok", "message": "已登出"}


@router.get("/me", response_model=UserProfileOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    has_resume = (
        await db.execute(select(Resume.id).where(Resume.user_id == user.id).limit(1))
    ).scalar_one_or_none() is not None
    profile = UserProfileOut(
        **UserOut.model_validate(user).model_dump(),
        has_parsed_resume=has_resume,
    )
    return profile

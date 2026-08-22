"""认证 API：注册、登录、获取个人信息。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models.resume import Resume
from app.models.user import User
from app.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut
from app.schemas.user import UserProfileOut

router = APIRouter(prefix="/auth", tags=["认证"])


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

    token = create_access_token(subject=str(user.id))
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


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

    token = create_access_token(subject=str(user.id))
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


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
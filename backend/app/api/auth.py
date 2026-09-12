"""认证 API：注册、登录、刷新令牌、登出、邮箱验证码、找回密码、获取个人信息。

双令牌体系：
- access  15 分钟，无状态，访问业务接口用
- refresh 7 天，jti 登记在 refresh_tokens 表，只有它能换新令牌对
- 登出/封禁 = 吊销 refresh（表里 revoked=True）；access 等它自然过期（≤15 分钟）
- 轮换：每次 refresh 都换发新的 refresh 并吊销旧的；
  「已吊销的 refresh 再次出现」= 重放攻击信号，吊销该用户全部 refresh

邮箱验证码承载两个场景（purpose 隔离）：
- register：注册时验证邮箱归属
- reset：找回密码（重置成功后吊销该用户全部 refresh，强制全端重新登录）
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
from app.schemas.auth import (
    ForgotPasswordIn,
    LoginIn,
    RefreshIn,
    RegisterIn,
    RegisterPolicyOut,
    ResetPasswordIn,
    SendEmailCodeIn,
    TokenOut,
    UserOut,
)
from app.schemas.user import UserProfileOut
from app.services.email import EmailNotConfigured
from app.services.email_code import (
    PURPOSE_RESET,
    CodeRateLimited,
    issue_code,
    verify_code,
)

import logging

router = APIRouter(prefix="/auth", tags=["认证"])

logger = logging.getLogger(__name__)


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

    # 邮箱归属校验：证明这个邮箱确实是他本人的，而不是随便填一个
    if settings.REQUIRE_EMAIL_VERIFY:
        if not payload.email_code:
            raise HTTPException(status_code=400, detail="请填写邮箱验证码")
        ok, reason = await verify_code(db, payload.email, payload.email_code)
        if not ok:
            raise HTTPException(status_code=400, detail=reason)

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return await _issue_token_pair(user, db)


@router.get("/register-policy", response_model=RegisterPolicyOut)
async def register_policy():
    """注册策略（公开接口）：告诉前端是否需要邮箱验证码。"""
    return RegisterPolicyOut(
        require_email_verify=settings.REQUIRE_EMAIL_VERIFY,
        email_configured=bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD),
    )


@router.post("/email/send-code")
async def send_email_code(payload: SendEmailCodeIn, db: AsyncSession = Depends(get_db)):
    """发送邮箱验证码（注册用）。

    刻意**不告知该邮箱是否已注册**：那会变成一个人人可用的「邮箱是否注册过」查询接口
    （用户枚举）。这里一律返回中性成功，注册时的占用提示才由 /register 给出。
    """
    await _send_code(db, payload.email, payload.purpose)
    return {"ok": True, "message": "验证码已发送，请查收邮件（含垃圾箱）"}


# ---------------- 找回密码 ----------------
# 复用同一张 email_verifications 表与同一套发码/校验/限流，只是 purpose 换成 reset。
# 刻意不复用 register 用途：两种场景的码必须隔离，否则「注册验证码」能改别人密码。


async def _send_code(db: AsyncSession, email: str, purpose: str) -> None:
    """调 issue_code 并把领域异常翻译成 HTTP 状态码（send-code 与 forgot 共用）。"""
    try:
        await issue_code(db, email, purpose)
    except CodeRateLimited as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
            headers={"Retry-After": str(e.retry_after)},
        ) from e
    except EmailNotConfigured as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="邮件服务尚未配置，请联系管理员",
        ) from e
    except Exception as e:
        # SMTP 连不上、被拒收、超时等。原始异常已由 email_code 记进日志，
        # 这里对用户只给一句通用提示，不把 SMTP 细节暴露出去
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="验证码发送失败，请稍后重试",
        ) from e


@router.post("/password/forgot", response_model=dict)
async def forgot_password(payload: ForgotPasswordIn, db: AsyncSession = Depends(get_db)):
    """请求「重置密码」验证码。

    防用户枚举：无论该邮箱是否注册过，对外都是同一句话。
    只在用户确实存在时才真的发信 —— 否则这个接口会变成「给任意邮箱发信」的工具。
    （响应耗时的细微差异理论上可被用来判断邮箱是否存在，但已有 60 秒冷却 +
    每小时上限，批量探测的成本远高于收益，这个场景下可以接受。）
    """
    user = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if user is not None:
        await _send_code(db, payload.email, PURPOSE_RESET)
    return {"ok": True, "message": "如果该邮箱已注册，验证码已发送（含垃圾箱）"}


@router.post("/password/reset", response_model=dict)
async def reset_password(payload: ResetPasswordIn, db: AsyncSession = Depends(get_db)):
    """用邮箱验证码重置密码，并吊销该用户全部 refresh token。

    为什么要连带吊销：触发「重置密码」的典型场景就是「账号可能已被他人控制」。
    如果旧设备上的登录态继续有效，改密码等于没改 —— 攻击者手里的 refresh token
    照样能续命。所以重置成功即全端下线，必须用新密码重新登录。

    附带效果（有意保留）：重置后若旧设备拿已吊销的 refresh 来续期，会命中
    /refresh 的重放检测，进而连带吊销该用户当时的所有会话 —— 用户表现为
    「需要重新登录一次」，与重置密码的预期一致，因此不做特例绕开。
    """
    user = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    # 邮箱不存在时也返回「验证码不正确」，不透露该邮箱是否注册
    if user is None:
        raise HTTPException(status_code=400, detail="验证码不正确或已过期")

    ok, reason = await verify_code(db, payload.email, payload.code, PURPOSE_RESET)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    user.hashed_password = hash_password(payload.new_password)
    await db.execute(
        update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True)
    )
    await db.commit()
    logger.info("用户 %s 通过邮箱验证码重置了密码，已吊销其全部 refresh token", user.id)
    return {"ok": True, "message": "密码已重置，请用新密码登录"}


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

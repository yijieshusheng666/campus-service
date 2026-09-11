"""安全工具：密码哈希（bcrypt/passlib） + 双令牌（access/refresh）签发与校验。

双令牌的核心分工：
- access token：短命（默认 15 分钟）、无状态、不入库。每个请求都带，泄漏损失窗口小。
- refresh token：长命（默认 7 天）、payload 带 jti，jti 登记在 refresh_tokens 表，
  登出 / 轮换 / 封禁 = 把表里那行 revoked 置 True —— 这就是 JWT「可吊销」的实现。
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str, expires_days: int | None = None) -> tuple[str, str]:
    """签发 refresh token，返回 (token, jti)。

    jti（JWT ID）是这张令牌在 refresh_tokens 表里的唯一登记号：
    调用方负责把 jti 连同过期时间写入表，之后吊销/轮换都按 jti 操作。
    """
    jti = str(uuid.uuid4())
    expire = datetime.now(timezone.utc) + timedelta(
        days=expires_days or settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {"sub": subject, "exp": expire, "type": "refresh", "jti": jti}
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti


def decode_token(token: str) -> dict:
    # PyJWT 默认校验 exp（过期抛 ExpiredSignatureError）与签名（伪造抛 InvalidSignatureError）
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

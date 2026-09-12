"""邮箱验证码的签发与校验。

安全要点（每一条都对应一种真实攻击）：
- 用 `secrets` 生成 6 位码，不用 `random`（random 是可预测的 PRNG，可被还原种子）
- 只存 sha256(email:code:SECRET_KEY)，防拖库后直接读出可用码、防彩虹表批量比对
- 同一邮箱 60 秒冷却 + 每小时 5 次上限，防拿平台当短信/邮件轰炸机
- 发新码时作废该邮箱同用途的旧码：否则同时有效的码会越来越多，猜测空间随之变大
- 校验失败累计 5 次即作废：6 位数字若不限次，几分钟就能暴力枚举完
- 校验成功后立刻标记 used_at：一次性使用，防重放
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.email_verification import EmailVerification
from app.services.email import EmailNotConfigured, build_code_email, send_email

logger = logging.getLogger(__name__)

PURPOSE_REGISTER = "register"
PURPOSE_RESET = "reset"
MAX_ATTEMPTS = 5


class CodeRateLimited(RuntimeError):
    """发送过于频繁。retry_after 为建议等待秒数。"""

    def __init__(self, message: str, retry_after: int = 0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _now() -> datetime:
    """naive UTC —— MySQL 的 DateTime 无时区，全库统一用这个口径。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_code(email: str, code: str) -> str:
    raw = f"{email.lower()}:{code}:{settings.SECRET_KEY}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def issue_code(db: AsyncSession, email: str, purpose: str = PURPOSE_REGISTER) -> None:
    """生成验证码、落库（存哈希）、发邮件。

    Raises:
        CodeRateLimited: 冷却期内重复请求，或超过每小时上限
        EmailNotConfigured: SMTP 未配置（调用方应转成 503 并提示运维）
    """
    email = email.lower()
    now = _now()

    # ---- 限流：先查最后一次发送时间与最近一小时次数 ----
    last = (
        await db.execute(
            select(EmailVerification.created_at)
            .where(EmailVerification.email == email, EmailVerification.purpose == purpose)
            .order_by(EmailVerification.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last is not None:
        elapsed = (now - last).total_seconds()
        if elapsed < 0:
            # 库里的时间落在「未来」——只可能来自两种原因：历史脏数据（早期该列由
            # MySQL NOW() 按 UTC+8 写入，比 Python 的 UTC 快 8 小时）或机器时钟偏差。
            # 此时绝不能当成「冷却中」：60 - (-25500) 会算出「请 25561 秒后再试」这种
            # 约 7 小时的荒谬等待。这里选择放行 + 留日志，让问题可见而不是静默锁死用户。
            logger.warning(
                "email_verifications 存在未来时间行（疑似时区/时钟不一致）："
                "email=%s, created_at=%s, utc_now=%s", email, last, now
            )
        elif elapsed < settings.EMAIL_CODE_COOLDOWN_SECONDS:
            wait = int(settings.EMAIL_CODE_COOLDOWN_SECONDS - elapsed)
            raise CodeRateLimited(f"请求过于频繁，请 {wait} 秒后再试", retry_after=wait)

    hour_count = (
        await db.execute(
            select(func.count(EmailVerification.id)).where(
                EmailVerification.email == email,
                EmailVerification.purpose == purpose,
                EmailVerification.created_at >= now - timedelta(hours=1),
            )
        )
    ).scalar_one()
    if hour_count >= settings.EMAIL_CODE_HOURLY_LIMIT:
        raise CodeRateLimited(
            f"该邮箱发送次数已达上限（每小时 {settings.EMAIL_CODE_HOURLY_LIMIT} 次），请稍后再试",
            retry_after=3600,
        )

    # ---- 生成并落库 ----
    code = f"{secrets.randbelow(1_000_000):06d}"
    # 旧码全部作废，保证「同一时刻只有一个有效码」
    await db.execute(
        update(EmailVerification)
        .where(
            EmailVerification.email == email,
            EmailVerification.purpose == purpose,
            EmailVerification.used_at.is_(None),
        )
        .values(used_at=now)
    )
    record = EmailVerification(
        email=email,
        purpose=purpose,
        code_hash=_hash_code(email, code),
        expires_at=now + timedelta(minutes=settings.EMAIL_CODE_TTL_MINUTES),
    )
    db.add(record)
    await db.commit()

    # 发信放在落库之后：发信失败时库里留一条未使用的码，下次重发会作废它，无害；
    # 反过来先发信后落库，一旦落库失败用户就会收到一个永远不会通过的码。
    subject, body = build_code_email(code, purpose)
    try:
        await send_email(email, subject, body)
    except EmailNotConfigured:
        # 邮件根本没发出去，就不该占用 60 秒冷却与每小时额度（否则 SMTP 一坏，
        # 用户重试被自己平台的限流挡住，反而更难排查）——把这条记录撤掉
        await db.delete(record)
        await db.commit()
        logger.error("SMTP 未配置，无法发送验证码邮件（email=%s）", email)
        raise
    except Exception:
        # 其它发信异常（网络超时、被邮件网关拒收等）同样撤销这次记录，
        # 但保留日志里的原始异常便于定位
        await db.delete(record)
        await db.commit()
        logger.exception("发送验证码邮件失败（email=%s）", email)
        raise


async def verify_code(
    db: AsyncSession, email: str, code: str, purpose: str = PURPOSE_REGISTER
) -> tuple[bool, str]:
    """校验验证码，返回 (是否通过, 失败原因)。通过后立即置为已使用。"""
    email = email.lower()
    row = (
        await db.execute(
            select(EmailVerification)
            .where(
                EmailVerification.email == email,
                EmailVerification.purpose == purpose,
                EmailVerification.used_at.is_(None),
            )
            .order_by(EmailVerification.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if row is None:
        return False, "请先获取邮箱验证码"
    if row.expires_at < _now():
        return False, "验证码已过期，请重新获取"
    if row.attempts >= MAX_ATTEMPTS:
        return False, "验证码错误次数过多，请重新获取"

    if not secrets.compare_digest(row.code_hash, _hash_code(email, code)):
        # 用 compare_digest 而非 == ：避免通过响应耗时差异逐位试出正确的哈希前缀
        row.attempts += 1
        await db.commit()
        remaining = MAX_ATTEMPTS - row.attempts
        return False, f"验证码不正确，还可尝试 {remaining} 次"

    row.used_at = _now()  # 一次性
    await db.commit()
    return True, ""

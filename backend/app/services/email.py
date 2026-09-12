"""邮件发送：目前只用于发邮箱验证码。

两个刻意的技术选择：
1. **用标准库 smtplib 而不是引入 aiosmtplib**：只发一封纯文本邮件，
   为它加一个依赖不划算；smtplib 是阻塞的，所以放进 asyncio.to_thread 执行，
   不阻塞事件循环（与 resumes.py 里 pdfplumber 的处理方式一致）。
2. **SMTP 未配置时明确报错，而不是静默降级**：静默降级会让人以为邮件发出去了，
   实际收不到，排查成本极高；宁可让接口返回一句「邮件服务未配置」。
"""
import asyncio
import logging
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from app.config import settings

logger = logging.getLogger(__name__)


class EmailNotConfigured(RuntimeError):
    """SMTP 未配置（部署时 .env 里没填 SMTP_HOST / SMTP_USER / SMTP_PASSWORD）。"""


def _send_sync(to_email: str, subject: str, body: str) -> None:
    """阻塞式发信，必须在线程池里调用。"""
    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise EmailNotConfigured("邮件服务未配置（SMTP_HOST / SMTP_USER / SMTP_PASSWORD）")

    sender = settings.SMTP_FROM or settings.SMTP_USER
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    # formataddr 处理发件人显示名含中文的情况（否则部分客户端显示乱码）
    msg["From"] = formataddr((str(Header(settings.SMTP_FROM_NAME, "utf-8")), sender))
    msg["To"] = to_email

    if settings.SMTP_USE_SSL:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(sender, [to_email], msg.as_string())
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(sender, [to_email], msg.as_string())


async def send_email(to_email: str, subject: str, body: str) -> None:
    """异步发信（内部走线程池）。配置缺失时抛 EmailNotConfigured，调用方转成 503。"""
    await asyncio.to_thread(_send_sync, to_email, subject, body)
    logger.info("邮件已发送至 %s，主题=%s", to_email, subject)


def build_code_email(code: str, purpose: str) -> tuple[str, str]:
    """生成验证码邮件的 (主题, 正文)。

    正文刻意写得朴素：纯文本、无链接、无 HTML —— 链接容易被邮件网关判为钓鱼，
    也会让用户养成「点邮件里的链接」的习惯。
    """
    action = "注册账号" if purpose == "register" else "重置密码"
    minutes = settings.EMAIL_CODE_TTL_MINUTES
    subject = f"【校园综合服务平台】{action}验证码"
    body = (
        f"您好：\n\n"
        f"您正在{action}，验证码是：{code}\n\n"
        f"验证码 {minutes} 分钟内有效，请勿泄露给任何人。\n"
        f"如果这不是您本人的操作，忽略本邮件即可，您的账号不会受到影响。\n\n"
        f"—— 校园综合服务平台"
    )
    return subject, body

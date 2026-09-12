"""应用配置：基于 pydantic-settings，从环境变量 / .env 读取。"""
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录的绝对路径（config.py 位于 backend/app/ 下）
BASE_DIR = Path(__file__).resolve().parent.parent
# .env 必须用绝对路径：pydantic-settings 的相对路径是相对「当前工作目录」解析的，
# 若从仓库根目录启动 uvicorn，就找不到 backend/.env，会静默回退到默认值（密码/模型全错）。
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "校园综合服务平台"
    APP_ENV: str = "dev"
    DEBUG: bool = True

    # --- 数据库 (MySQL 8.0, async driver) ---
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "root"
    DB_NAME: str = "campus_platform"
    DB_ECHO: bool = False
    DATABASE_URL: str = ""

    # --- JWT ---
    SECRET_KEY: str = "CHANGE_ME_campus_platform_secret"
    JWT_ALGORITHM: str = "HS256"
    # 双令牌体系：access 短命（泄漏损失窗口小），refresh 长命但入库可吊销。
    # ⚠️ 服务器 .env 里若仍写着旧值 10080 会覆盖这里，部署时需同步改 .env。
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- 邮箱验证码 / SMTP ---
    # REQUIRE_EMAIL_VERIFY=True 时，注册必须携带有效的邮箱验证码（见 api/auth.py）。
    # 默认 False：SMTP 没配好之前不影响现有注册流程，配好后再在 .env 里翻开关。
    REQUIRE_EMAIL_VERIFY: bool = False
    EMAIL_CODE_TTL_MINUTES: int = 10      # 验证码有效期
    EMAIL_CODE_COOLDOWN_SECONDS: int = 60  # 同一邮箱两次发送的最小间隔
    EMAIL_CODE_HOURLY_LIMIT: int = 5       # 同一邮箱每小时最多发几次（防刷）
    # SMTP：留空则「发送验证码」接口返回 503 并说明未配置，不会静默失败。
    # QQ 邮箱示例：smtp.qq.com / 465 / SSL，SMTP_PASSWORD 填「授权码」而不是登录密码
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""       # 留空则用 SMTP_USER
    SMTP_FROM_NAME: str = "校园综合服务平台"
    SMTP_USE_SSL: bool = True  # 465→True(SSL)；587→False(STARTTLS)

    # --- 上传存储 ---
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    STATIC_URL: str = "/static"
    MAX_UPLOAD_SIZE_MB: int = 10

    # --- LLM：OpenAI 兼容 API（默认智谱 GLM，也可换成任意兼容网关） ---
    # ⚠️ 换模型只改 backend/.env，不要改这里的默认值
    LLM_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "glm-4.5-flash"
    # 视觉模型（多模态商品识别用）：之前硬编码在 goods_agent.py 里，现改为可配置
    LLM_VISION_MODEL: str = "glm-4v-flash"
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 4096
    # 本地 Ollama 时使用（走 ChatOllama 分支）
    OLLAMA_HOST: str = "http://localhost:11434"

    @field_validator("UPLOAD_DIR")
    @classmethod
    def _abs_upload_dir(cls, v: str) -> str:
        """把相对的上传目录解析为绝对路径。

        否则 StaticFiles 挂载与文件写入都会随「启动时的工作目录」漂移，
        从不同目录启动就会读写到不同的 uploads/，图片表现为 404。
        """
        p = Path(v).expanduser()
        return str(p if p.is_absolute() else (BASE_DIR / p))

    @field_validator("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME")
    @classmethod
    def _ascii_only(cls, v: str, info) -> str:
        """数据库连接参数必须是 ASCII。

        MySQL 握手协议用 latin-1 编码传输这些字段。一旦含中文（最常见的情况是
        .env.example 被直接复制成 .env、中文占位符原样留着没改），就会在 asyncmy
        建连时抛出一句毫无线索的
            UnicodeEncodeError: 'latin-1' codec can't encode characters ...
        最终只表现为 "ERROR: Application startup failed. Exiting."，极难定位。
        这里提前拦下并直接说清该怎么改。
        """
        if any(ord(c) > 127 for c in v):
            raise ValueError(
                f"{info.field_name} 含非 ASCII 字符（当前值 {v!r}）。"
                f"这通常说明 backend/.env 还是从 .env.example 复制过来的、占位符没改。"
                f"请打开 backend/.env 填入真实的数据库配置（不能含中文）。"
            )
        return v

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def sqlalchemy_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"mysql+asyncmy://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


# pydantic-settings 自带单例缓存，无需手动 lru_cache
settings = Settings()
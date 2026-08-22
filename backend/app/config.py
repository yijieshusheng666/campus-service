"""应用配置：基于 pydantic-settings，从环境变量 / .env 读取。"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # --- 上传存储 ---
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    STATIC_URL: str = "/static"
    MAX_UPLOAD_SIZE_MB: int = 10

    # --- LLM：OpenAI 兼容 API（默认智谱 v4，也可换成任意兼容网关） ---
    LLM_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "glm-4-flash"
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 2048
    # 本地 Ollama 时使用（走 ChatOllama 分支）
    OLLAMA_HOST: str = "http://localhost:11434"

    # --- CORS ---
    CORS_ORIGINS: str = "*"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
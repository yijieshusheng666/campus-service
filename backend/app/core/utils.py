"""通用工具：分页、id 编码、上传文件安全。"""
import secrets
import uuid
from pathlib import Path


def new_id() -> str:
    """对外暴露的短 id，避免暴露自增主键。"""
    return uuid.uuid4().hex[:16]


def safe_filename(original: str, prefix: str = "") -> str:
    """生成安全的存储文件名，丢弃用户原始路径与危险字符。"""
    suffix = Path(original).suffix.lower()
    return f"{prefix}{secrets.token_hex(8)}{suffix}"


ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
ALLOWED_PDF_EXT = {".pdf"}
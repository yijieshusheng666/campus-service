"""通用工具：上传文件安全。"""
import secrets
from pathlib import Path


def safe_filename(original: str, prefix: str = "") -> str:
    """生成安全的存储文件名，丢弃用户原始路径与危险字符。"""
    suffix = Path(original).suffix.lower()
    return f"{prefix}{secrets.token_hex(8)}{suffix}"


def escape_like(keyword: str) -> str:
    r"""转义 SQL LIKE 通配符（% _ \），防止用户输入干扰匹配语义。MySQL 默认转义符为反斜杠。"""
    return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
ALLOWED_PDF_EXT = {".pdf"}

# 常见图片格式的文件头魔数：扩展名可伪造，按内容二次校验
_IMAGE_MAGICS = (
    b"\xff\xd8\xff",       # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"GIF87a",
    b"GIF89a",
    b"BM",                 # BMP
)


def looks_like_image(head: bytes) -> bool:
    return any(head.startswith(m) for m in _IMAGE_MAGICS) or (
        head[:4] == b"RIFF" and head[8:12] == b"WEBP"  # WEBP：RIFF 容器
    )
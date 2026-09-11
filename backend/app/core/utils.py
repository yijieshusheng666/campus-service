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
# 简历支持的格式：PDF + Word 新版格式。
# 旧版 .doc 是二进制专有格式，解析得靠 antiword / LibreOffice 这类外部程序，
# 在服务器上引入这些依赖不值当 —— 上传接口会明确提示用户「另存为 .docx」。
ALLOWED_RESUME_EXT = {".pdf", ".docx"}

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


def looks_like_pdf(head: bytes) -> bool:
    return head.startswith(b"%PDF-")


def looks_like_docx(head: bytes) -> bool:
    """.docx 本质是 ZIP 容器，文件头为 PK\\x03\\x04。

    用户常犯的错是把别的文件直接改后缀成 .docx，这里按内容二次确认，
    否则解析阶段会抛出一句完全看不懂的 zipfile.BadZipFile。
    """
    return head.startswith(b"PK\x03\x04")
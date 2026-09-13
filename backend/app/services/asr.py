"""语音转写：调用智谱 GLM-ASR（OpenAI 兼容 `/audio/transcriptions`）。

面试回答的语音入口。设计要点：

- **复用密钥**：走 `LLM_BASE_URL` + `LLM_API_KEY`，与文本模型同一账户，不引入新供应商；
- **切片责任在前端**：智谱硬限制「单段 ≤30 秒 / ≤25MB」，后端只校验不切分。前端滚动
  每 30 秒切一片逐片提交，避免在后端引入 ffmpeg / pydub 这类音频处理依赖；
- **上下文延续**：调用方把上一段的转写结果作为 `prompt` 传入（官方建议用法），
  缓解切片处的语义断裂，比机械拼接更接近完整句子；
- **热词表**：从简历抽取技术名词提交给 ASR，显著提升「WebSocket / 召回率 / 幂等」
  这类术语的识别率。热词被拒时自动去掉重试，不让它成为单点故障；
- **退避重试**：ASR 与文本模型共享同一份免费额度，高峰期必撞 429。
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ASR_PATH = "/audio/transcriptions"

# 单次请求的尝试次数与退避间隔（秒）：ASR 与文本模型抢同一份配额，429 很常见
_MAX_ATTEMPTS = 3
_BACKOFF = (1.0, 3.0)

# prompt 上下文保留的尾部长度：官方建议 <8000 字，这里取远小于它的值——
# 上下文的作用只是让切片处断句连续，不需要把前文全带上（也省 token）
_PROMPT_TAIL_CHARS = 2000
# 热词数量上限（官方建议不超过 100）
_MAX_HOTWORDS = 100


class ASRError(RuntimeError):
    """转写失败（配置缺失、音频非法、上游错误）。调用方据此返回 4xx/5xx。"""


# 技术名词白名单：命中简历才提交给 ASR。
# 刻意用白名单而非「正则抽英文词」——后者会把公司名、地名、姓名拼音一起带进去，
# 反而干扰识别（热词表是精确匹配用的，塞噪声不如不传）。
TECH_HOTWORDS: tuple[str, ...] = (
    # 语言与框架
    "Python", "Java", "Vue", "React", "FastAPI", "LangChain", "Spring",
    # 数据与中间件
    "MySQL", "Redis", "PostgreSQL", "SQL", "索引", "事务", "分库分表",
    # 工程与部署
    "Docker", "Nginx", "Git", "GitHub", "CI", "CD", "Uvicorn", "Alembic",
    "反向代理", "负载均衡", "systemd", "幂等",
    # 协议与规范
    "API", "RESTful", "WebSocket", "SSE", "HTTP", "JSON", "OAuth", "JWT", "RBAC",
    # AI 相关
    "LLM", "Agent", "RAG", "Prompt", "Token", "Embedding", "Chroma", "向量检索",
    "召回率", "多模态", "流式输出", "幻觉", "微调", "上下文窗口",
    # 常见工程话题
    "并发", "原子性", "状态机", "依赖注入", "分页", "限流", "缓存", "回归测试",
    "单元测试", "pytest", "迁移", "回滚", "可观测性",
)


def extract_hotwords(resume_text: str, limit: int = _MAX_HOTWORDS) -> list[str]:
    """从简历文本抽取技术名词作为 ASR 热词；纯字符串匹配，不调用 LLM。"""
    text = (resume_text or "").lower()
    if not text:
        return []
    hits = [w for w in TECH_HOTWORDS if w.lower() in text]
    return hits[:limit]


def _build_fields(prompt: str, hotwords: list[str] | None) -> dict:
    """构造 multipart 表单字段（不含 file）。

    ⚠️ 这里必须返回 **dict**，不能是 list of tuples：httpx 的 encode_request 只在
    `data` 是 Mapping 时才走 multipart 编码，否则会把它当成「原始请求体」并生成
    **同步** ByteStream，进而在 AsyncClient 上抛
    `RuntimeError: Attempted to send an sync request with an AsyncClient instance.`
    —— 报错信息完全不指向真正原因，排查成本极高（已踩过）。

    数组型参数（hotwords）因此在 multipart 里用 JSON 字符串表达。
    """
    fields: dict = {"model": settings.ASR_MODEL, "stream": "false"}
    if prompt:
        fields["prompt"] = prompt[-_PROMPT_TAIL_CHARS:]
    if hotwords:
        fields["hotwords"] = json.dumps(list(hotwords[:_MAX_HOTWORDS]), ensure_ascii=False)
    return fields


async def _post_once(url: str, api_key: str, audio: bytes, filename: str,
                     fields: dict) -> httpx.Response:
    """发出一次转写请求（multipart）。"""
    async with httpx.AsyncClient(timeout=settings.ASR_TIMEOUT) as client:
        return await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (filename, audio, "audio/wav")},
            data=fields,
        )


def _extract_text(payload: dict) -> str:
    """从响应体中取转写文本（OpenAI 兼容结构：{"text": "..."}）。"""
    if not isinstance(payload, dict):
        return ""
    text = payload.get("text")
    if isinstance(text, str):
        return text.strip()
    # 部分兼容实现把结果放在 choices[0].message.content
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") or {}
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"].strip()
    return ""


async def transcribe(
    audio: bytes,
    filename: str = "answer.wav",
    prompt: str = "",
    hotwords: list[str] | None = None,
) -> str:
    """把一段音频转写为文本；失败抛 ASRError。

    Args:
        audio: 音频字节（未压缩 PCM 的 WAV，≤ASR_MAX_BYTES）
        filename: 上传文件名（仅用于 multipart 头）
        prompt: 上一段转写结果，用于保持跨切片的语义连续
        hotwords: 热词表（见 extract_hotwords）
    """
    if not audio:
        raise ASRError("音频内容为空")
    if len(audio) > settings.ASR_MAX_BYTES:
        limit_mb = settings.ASR_MAX_BYTES // (1024 * 1024)
        raise ASRError(f"单段音频超过 {limit_mb}MB，请缩短录音后重试")

    api_key = (settings.LLM_API_KEY or "").strip()
    if not api_key:
        raise ASRError("未配置 LLM_API_KEY，无法调用语音识别")

    url = settings.LLM_BASE_URL.rstrip("/") + ASR_PATH
    fields = _build_fields(prompt, hotwords)

    last_error = ""
    for attempt in range(_MAX_ATTEMPTS):
        # 首次带热词；若上游因参数不认（4xx）则后续尝试去掉热词——热词是增强项，
        # 不能因为格式兼容问题让整个转写失败。
        current = fields if attempt == 0 else {k: v for k, v in fields.items() if k != "hotwords"}
        try:
            resp = await _post_once(url, api_key, audio, filename, current)
        except Exception as e:  # 网络异常 / 超时：重试
            last_error = f"{type(e).__name__}: {e}"
            logger.warning("ASR 请求异常（第 %d 次）：%s", attempt + 1, last_error)
        else:
            if resp.status_code == 200:
                text = _extract_text(resp.json() if resp.content else {})
                logger.info(
                    "ASR 转写成功：音频 %d 字节，热词 %d 个，文本 %d 字",
                    len(audio), len(fields.get("hotwords") or []), len(text),
                )
                return text
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning("ASR 返回错误（第 %d 次）：%s", attempt + 1, last_error)
            # 4xx 多为参数问题：降级（下次不带热词）后立即重试，不必等退避
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                if attempt == 0 and "hotwords" in fields:
                    continue
                raise ASRError(f"语音识别服务拒绝了请求：{last_error}")
        if attempt < _MAX_ATTEMPTS - 1:
            await asyncio.sleep(_BACKOFF[min(attempt, len(_BACKOFF) - 1)])

    raise ASRError(f"语音识别失败（重试 {_MAX_ATTEMPTS} 次）：{last_error}")

"""二手商品发布助手 Agent：图片 + 描述 → 结构化商品信息 + 定价建议。

设计要点（面试讲点）：
- 多模态视觉识别：调用 GLM-4V-Flash 免费视觉模型直读图片，告别纯文本猜图；
- 定价是 RAG：查询同类商品历史成交价作为参考，再让 LLM 综合判断；
- 失败回退：LLM 解析异常或超时 → 返回空建议，前端保持手动填写，不阻塞流程；
- 仅引 langchain-core，复用现有 _build_llm，无新增依赖。
"""
from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.services.llm import _build_llm, _msg_text

logger = logging.getLogger(__name__)

VISION_MODEL = "glm-4v-flash"  # 智谱免费视觉模型，OpenAI 兼容接口

# 商品发布助手 system prompt（针对视觉模型优化）
AGENT_SYSTEM = """你是一位校园二手交易平台的商品发布助手。请根据卖家上传的商品图片和文字描述，准确识别商品信息并生成专业的发布内容。

输出格式（严格 JSON，不要 markdown 代码块）：
{
    "title": "商品标题（15-25字，突出品牌+型号+核心卖点）",
    "description": "商品描述（80-150字，说明入手渠道、使用状况、转手原因、交易地点）",
    "category": "分类（必须从以下选择：数码电子/教材教辅/生活用品/服饰鞋包/美妆护肤/运动户外/其他）",
    "condition": "成色（必须从以下选择：全新/九成新/八成新/七成新/五成新/其他）",
    "suggested_price": 建议价格（整数，参考校园二手市场行情）
}

视觉识别规则：
1. 仔细观察图片中的品牌标识、型号标签、外观细节
2. 数码产品注意：屏幕尺寸、存储容量、颜色、配件（充电器/耳机/保护壳等）
3. 书籍注意：书名、出版社、版次、是否有笔记划痕
4. 服饰注意：尺码、材质、品牌标签
5. 如果多图角度不同，综合判断商品完整信息

文案规则：
1. 标题要具体：包含品牌、型号、关键规格（如"iPad Air 5 64G 星光色 带原装笔"）
2. 描述诚实：主动说明瑕疵或使用痕迹，不要夸大
3. 成色判断保守：有明显划痕/使用痕迹 → 八成新；几乎无痕迹 → 九成新
4. 定价策略：比市场价略低 10-20%，突出"校园面交/可小刀"促进成交
5. 如果图片信息不足，category 和 condition 给出最可能的猜测，不要留空
"""

# 定价专家 system prompt（接收历史成交价作为参考）
PRICE_SYSTEM = """你是一位校园二手交易定价专家。请根据商品信息和历史成交数据给出定价建议。

输出格式（严格 JSON）：
{
    "min_price": 最低建议价（整数）,
    "max_price": 最高建议价（整数）,
    "recommended": 推荐快速出售价（整数，min 和 max 之间偏左）,
    "reasoning": "定价理由（40字以内，说明参考依据）"
}

定价原则：
- 全新未拆封：原价 7-8 折
- 九成新（几乎无痕迹）：原价 5-6 折
- 八成新（轻微使用痕迹）：原价 3-4 折
- 七成新及以下：原价 2 折或更低
- 教材教辅：原价 3-5 折，热门/绝版教材可上浮
- 电子数码贬值快：参考发布年限，每年折旧 15-25%
"""


# ---- 图片转 base64 data URL（让视觉模型无需联网即可看图） ----


def _image_url_to_base64_dataurl(url: str) -> str | None:
    """将图片 URL（本地路径或 http URL）转为 base64 data URL，供多模态消息使用。"""
    if not url:
        return None
    try:
        # 解析 URL
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            import httpx
            response = httpx.get(url, timeout=15)
            response.raise_for_status()
            content = response.content
        else:
            # 本地路径：去掉 / 前缀后基于上传目录查找
            # URL 格式通常是 /static/goods/img_xxx.png
            relative_path = url.lstrip("/")
            upload_dir = Path(settings.UPLOAD_DIR) / "goods"
            # 尝试从 URL 提取文件名
            fname = Path(url).name
            candidate = upload_dir / fname
            if candidate.exists():
                content = candidate.read_bytes()
            else:
                # 尝试完整相对路径
                full_path = Path(settings.UPLOAD_DIR).parent / relative_path
                if full_path.exists():
                    content = full_path.read_bytes()
                else:
                    logger.warning("图片文件不存在，跳过 base64 转换: %s", url)
                    return None

        # 检测 MIME 类型（简单按扩展名）
        suffix = Path(url).suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        mime = mime_map.get(suffix, "image/png")
        b64 = base64.b64encode(content).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception as e:
        logger.warning("图片转 base64 失败 %s: %s", url, e)
        return None


def _absolute_image_url(url: str, base_url: str | None = None) -> str:
    """确保图片 URL 是绝对路径（视觉模型需要可访问的 URL）。

    如果 URL 是相对路径（如 /static/goods/xxx.jpg），拼接 base_url 前缀。
    默认 base_url 从 settings 读取 STATIC_URL 的域名部分。
    """
    if not url:
        return url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    # 相对路径，需要拼接
    if base_url is None:
        from app.config import settings
        base = (settings.STATIC_URL or "").rstrip("/")
        # STATIC_URL 本身可能是 /static，需要补全协议和 host
        if not base.startswith("http"):
            # 兜底：假设前端通过当前域名访问，这里尝试从 SERVER_HOST 等推断
            # 最安全的做法：base_url 传完整的 request.base_url 进来
            base = ""
    else:
        base = base_url.rstrip("/")
    if base:
        return f"{base}{url}"
    return url  # 仍然是相对路径，让调用方自行处理


def _make_multimodal_content(image_urls: list[str], user_hint: str) -> list[dict]:
    """构建多模态消息内容列表，供 GLM-4V-Flash 等视觉模型使用。

    核心改进：将图片转为 base64 data URL，视觉模型无需联网即可"看到"图片内容，
    避免 localhost 图片对外网不可访问导致识别错误。

    OpenAI 兼容格式：
    [
        {"type": "text", "text": "..."},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo..."}},
        ...
    ]
    """
    content: list[dict] = []
    if user_hint and user_hint.strip():
        content.append({"type": "text", "text": f"【卖家描述】\n{user_hint.strip()}\n\n请根据以上图片和描述生成商品发布信息，严格按 JSON 格式输出。"})
    else:
        content.append({"type": "text", "text": "卖家未提供文字描述，请根据商品图片直接识别并生成商品发布信息，严格按 JSON 格式输出。"})

    for url in image_urls:
        if not url:
            continue
        # 优先转 base64 data URL，确保视觉模型能直接读取
        data_url = _image_url_to_base64_dataurl(url)
        if data_url:
            content.append({"type": "image_url", "image_url": {"url": data_url}})
        else:
            # 回退：尝试用绝对 URL
            abs_url = _absolute_image_url(url)
            logger.warning("base64 转换失败，回退到绝对 URL（可能无法访问）: %s", abs_url)
            content.append({"type": "image_url", "image_url": {"url": abs_url}})

    return content


async def analyze_goods(image_urls: list[str], user_hint: str = "") -> dict:
    """分析商品信息，生成发布建议（多模态视觉识别版）。

    Args:
        image_urls: 已上传的商品图片 URL 列表（视觉模型直接读取）
        user_hint: 用户提供的初步描述或提示

    Returns:
        {
            "title": str,
            "description": str,
            "category": str,
            "condition": str,
            "suggested_price": int,
        }
    """
    logger.info("analyze_goods 调用，image_urls=%s, user_hint=%s", image_urls, user_hint)
    if not image_urls and not user_hint:
        return _empty_suggestion()

    # 使用视觉模型
    llm = _build_llm(model=VISION_MODEL)

    multimodal_content = _make_multimodal_content(image_urls, user_hint)
    logger.info(
        "多模态消息内容: 文本=%r，图片数=%d（urls=%s）",
        multimodal_content[0].get("text") if multimodal_content else "",
        sum(1 for m in multimodal_content if m.get("type") == "image_url"),
        image_urls,
    )

    msgs = [
        SystemMessage(content=AGENT_SYSTEM),
        HumanMessage(content=multimodal_content),
    ]

    try:
        raw = await llm.ainvoke(msgs)
        text = _msg_text(raw)
        logger.info("视觉模型原始返回: %s", text[:200])
        result = _extract_json(text)
        if result:
            return {
                "title": str(result.get("title", "")).strip(),
                "description": str(result.get("description", "")).strip(),
                "category": str(result.get("category", "其他")).strip(),
                "condition": str(result.get("condition", "九成新")).strip(),
                "suggested_price": _to_int(result.get("suggested_price", 0)),
            }
    except Exception as e:
        logger.error("analyze_goods (vision) failed: %s", e)
        logger.exception("详细错误:")

    return _empty_suggestion()


async def suggest_price(
    category: str, condition: str, description: str, price_range_text: str
) -> dict:
    """基于历史成交价给出定价建议。

    Args:
        category: 商品分类
        condition: 成色
        description: 商品描述
        price_range_text: 同类商品历史成交价区间描述（如 "¥50-100，平均 ¥75"）

    Returns:
        {
            "min_price": int,
            "max_price": int,
            "recommended": int,
            "reasoning": str,
        }
    """
    llm = _build_llm()
    system = PRICE_SYSTEM + f"""

【当前商品信息】
分类：{category}
成色：{condition}
描述：{description}
历史成交价参考：{price_range_text}
"""

    msgs = [
        SystemMessage(content=system),
        HumanMessage(content="请给出定价建议，严格按 JSON 格式输出。"),
    ]

    try:
        raw = await llm.ainvoke(msgs)
        text = _msg_text(raw)
        result = _extract_json(text)
        if result:
            return {
                "min_price": _to_int(result.get("min_price", 0)),
                "max_price": _to_int(result.get("max_price", 0)),
                "recommended": _to_int(result.get("recommended", 0)),
                "reasoning": str(result.get("reasoning", "")).strip(),
            }
    except Exception as e:
        logger.error("suggest_price failed: %s", e)

    return {
        "min_price": 0,
        "max_price": 0,
        "recommended": 0,
        "reasoning": "分析失败，请手动定价",
    }


# ---- 内部工具函数 ----

def _extract_json(text: str) -> dict | None:
    """从文本中提取 JSON 对象（支持 markdown 代码块）。"""
    if not text:
        return None

    # 优先匹配 markdown 代码块
    code_block = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if code_block:
        text = code_block.group(1)

    stripped = text.strip()
    # 模型可能返回 JSON 数组（如 [ {...}, {...} ]），取第一个对象
    if stripped.startswith("["):
        try:
            arr = json.loads(stripped)
            if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                return arr[0]
        except json.JSONDecodeError:
            pass

    # 匹配第一个 { ... }
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return None


def _to_int(value) -> int:
    """安全转整数，失败回退 0。"""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def _empty_suggestion() -> dict:
    return {
        "title": "",
        "description": "",
        "category": "其他",
        "condition": "九成新",
        "suggested_price": 0,
    }

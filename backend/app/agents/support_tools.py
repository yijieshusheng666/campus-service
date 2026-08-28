"""智能客服工具函数集（纯函数形式，供状态机直接调用）。

所有工具均为纯函数，不依赖 langchain BaseTool，由 support_agent.py 的状态机直接调用。
设计要点（面试讲点）：
- 分析工具只读：analyze_goods_draft 调用 goods_agent.analyze_goods，不写入数据库；
- 写入工具需确认：generate_publish_payload 仅构建发布参数，等用户 confirm_publish 才标记完成；
- 状态同步：每个工具执行时更新 SupportSessionState 的阶段和进度，保证状态机一致性。
"""
from __future__ import annotations

import logging

from app.agents.goods_agent import analyze_goods as _goods_analyze
from app.agents.support_state import PublishGoodsPhase, SupportSessionState

logger = logging.getLogger(__name__)

__all__ = [
    "analyze_goods_draft",
    "generate_publish_payload",
    "confirm_publish",
    "cancel_task",
    "reset_to_idle",
    "format_analysis_for_chat",
    "format_publish_payload_for_chat",
]


async def analyze_goods_draft(state: SupportSessionState) -> str:
    """分析商品草稿（只读）：根据已收集的图片和描述生成商品信息。

    前置条件：state.collected_images 至少有一张图片。
    成功：state.phase -> awaiting_confirm，返回分析结果文本。
    失败：state.phase -> collecting_images，返回错误文本。
    """
    state.phase = PublishGoodsPhase.analyzing
    if not state.collected_images:
        state.phase = PublishGoodsPhase.collecting_images
        return "[分析失败：请先上传至少一张商品图片]"

    try:
        result = await _goods_analyze(state.collected_images, state.user_hint)
        # 空结果保护：识别失败时回退收集阶段，不让用户确认空商品（失败回退需求）
        if not result or not str(result.get("title", "")).strip():
            state.phase = PublishGoodsPhase.collecting_images
            state.last_error = "图片识别结果为空"
            return "[分析失败：未能识别出商品信息，请更换更清晰/无死链的图片，或直接补充品牌型号等描述]"
        state.set_analysis_result(result)
        return format_analysis_for_chat(result)
    except Exception as e:
        state.phase = PublishGoodsPhase.collecting_images
        logger.error("analyze_goods_draft 失败: %s", e)
        return f"[分析失败：{e}，已回退到图片收集阶段，请重新上传或补充描述]"


def generate_publish_payload(state: SupportSessionState) -> str:
    """生成发布参数（仅构建，不写入数据库）。

    前置条件：state.analysis_result 已存在（用户已确认分析结果）。
    成功：state.phase -> awaiting_publish，返回发布参数预览文本。
    """
    if not state.analysis_result:
        return "[生成失败：没有可用的分析结果，请先执行 analyze_goods_draft]"

    try:
        state.confirm_analysis()
        payload = state.publish_payload
        return format_publish_payload_for_chat(payload)
    except Exception as e:
        logger.error("generate_publish_payload 失败: %s", e)
        return f"[生成失败：{e}]"


def confirm_publish(state: SupportSessionState) -> str:
    """确认发布：标记状态机为完成（实际写入由前端/上层 API 执行）。

    前置条件：state.publish_payload 已存在。
    成功：state.phase -> published，返回完成提示。
    """
    if not state.publish_payload:
        return "[发布失败：没有待发布的商品参数，请先执行 generate_publish_payload]"
    state.mark_published()
    title = state.publish_payload.get("title", "")
    return f"[商品《{title}》已准备就绪] 请在网页上点击最终确认按钮完成发布。"


def cancel_task(state: SupportSessionState, reason: str = "用户取消") -> str:
    """取消当前任务。"""
    state.mark_cancelled(reason)
    return f"[任务已取消：{reason}]"


def reset_to_idle(state: SupportSessionState) -> str:
    """重置为空闲状态。"""
    was_task = state.task.value if state.task else "idle"
    state.reset_task()
    return f"[状态已重置，当前为空闲。上一个任务：{was_task}]"


# ---- 格式化辅助函数 ----


def format_analysis_for_chat(result: dict) -> str:
    """将商品分析结果格式化为客服聊天文本。"""
    return (
        f"📦 AI 分析结果：\n"
        f"标题：{result.get('title', '')}\n"
        f"分类：{result.get('category', '')}\n"
        f"成色：{result.get('condition', '')}\n"
        f"建议价：¥{result.get('suggested_price', 0)}\n"
        f"描述：{result.get('description', '')[:80]}...\n\n"
        f"这个分析结果对吗？回复「确认」使用当前结果，或「修改」重新分析。"
    )


def format_publish_payload_for_chat(payload: dict) -> str:
    """将发布参数格式化为客服聊天文本。"""
    return (
        f"✅ 商品信息已确认：\n"
        f"标题：{payload.get('title', '')}\n"
        f"分类：{payload.get('category', '')}\n"
        f"成色：{payload.get('condition', '')}\n"
        f"价格：¥{payload.get('price', 0)}\n"
        f"图片数：{len(payload.get('image_urls', []))} 张\n\n"
        f"回复「发布」正式发布商品，或「取消」放弃发布。"
    )

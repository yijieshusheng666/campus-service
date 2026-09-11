"""全平台智能客服 Agent（v2 行动型）：LLM 问答 + 状态机驱动的商品发布助手。

架构（v1 纯问答 -> v2 行动型）：
- v1：嵌入式 RAG + per-user 会话记忆（保留为普通问答通道 _general_chat）；
- v2：在问答之上叠加"任务状态机 + 工具绑定"，支持帮用户跑完
  「发布二手商品」全流程：收图 -> AI 分析 -> 确认 -> 生成发布参数 -> 发布确认。

核心设计（面试讲点）：
1. 状态机驱动而非 LLM 自由 ReAct（v2 关键取舍）：
   每个阶段的动作是确定性代码逻辑，LLM 不负责状态决策——避免幻觉导致状态错乱；
   LLM 只负责生成回复文本 + 商品图片分析（复用 goods_agent.analyze_goods）。
2. 工具绑定 _bind_tools(state)：把纯函数工具绑定到当前会话状态，返回"工具注册表"
   （与 Function Calling 工具集语义对齐：名字 + 输入输出契约），状态机按阶段分派执行；
   llm.py 的 _bind_tools 用于需要 LLM 自由调用工具的扩展场景，二者并存。
3. 写操作安全：任何写入/发布动作只「生成参数 + 用户确认」，实际数据库写入仍由业务 API 完成；
4. 失败回退（can_transition 兜底）：分析失败自动回退 collecting_images，不丢已收集图片；
5. 会话隔离：per-user 状态机缓存（TTL 30 分钟），任务完成/取消后自动清理。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from functools import partial
from typing import Any, AsyncGenerator, Callable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agents.goods_agent import _image_url_to_base64_dataurl
from app.agents.support_state import (
    PublishGoodsPhase,
    SupportSessionState,
    TaskType,
)
from app.agents.support_tools import (
    analyze_goods_draft,
    cancel_task,
    confirm_publish,
    generate_publish_payload,
    reset_to_idle,
)
from app.config import settings
from app.services.llm import _build_llm, _msg_text

logger = logging.getLogger(__name__)

# ---- 全平台知识库（嵌入式 RAG，普通问答用） ----
SUPPORT_KNOWLEDGE = """
【平台概述】
校园综合服务平台是一个面向高校学生的综合服务应用，包含二手交易、校园跑腿、AI求职、站内私信四大板块。

【二手交易】
1. 发布商品：进入"发布宝贝"页，上传图片（最多6张），点击"AI帮我写"可让AI自动识别商品信息并生成标题、描述、分类、成色和定价建议。
2. 浏览商品：在"商品集市"查看所有在售商品，支持搜索和筛选。
3. 收藏商品：点击商品卡片上的爱心图标收藏，在"我的收藏"中查看。
4. 购买下单：点击商品进入详情页，点击"立即购买"下单，在我的订单中查看订单状态。
5. 图片上传：支持 JPG、PNG、WEBP 格式，单张不超过 10MB。

【校园跑腿】
1. 发布需求：进入"发布跑腿需求"，填写取件地址（如菜鸟驿站）、快递信息（如顺丰单号）、送达地址（如宿舍楼）、报酬金额和期望送达时间。
2. 接单大厅：在"跑腿大厅"查看所有待接单需求，点击接单赚取报酬。
3. 配送流程：接单后配送中 → 送达后点击"已送达" → 发布者确认结算。
4. 取消规则：仅待接单状态的需求可由发布者取消。
5. 防并发抢单：系统使用数据库原子更新，确保同一时间只有一个跑腿员能成功接单。

【AI求职】
1. 简历上传：在"我的简历"页面上传 PDF 简历，AI 自动解析姓名、电话、邮箱、教育背景、工作经历等字段。
2. 简历优化：AI 根据简历内容给出优化建议（格式、内容、关键词等），建议持久化显示。
3. 模拟面试：进入"AI模拟面试"，选择简历和面试岗位，AI 面试官会基于简历内容针对性提问。
4. 面试报告：面试结束后生成结构化评估报告，包含技术能力、表达能力、逻辑思维、综合素质四个维度的评分和改进建议。
5. 面试特性：ReAct 架构，支持工具调用（追问/查重/评估/结束），SSE 流式输出。

【站内私信】
1. 发起聊天：在商品详情页点击"联系卖家"或在设置页搜索用户发起私信。
2. 实时聊天：基于 WebSocket 的实时消息推送，支持离线消息落库和上线后补拉。
3. 未读消息：右上角消息图标显示未读数，30秒轮询更新。

【账号相关】
1. 注册登录：使用用户名+邮箱+密码注册，登录支持用户名或邮箱作为账号。
2. 密码修改：在"账号设置"中修改密码，需要验证当前密码。
3. 退出登录：点击侧边栏底部的退出图标安全退出。
"""

SUPPORT_SYSTEM = f"""你是一位校园综合服务平台的智能客服助手，亲切、专业、有耐心。你的职责是帮助学生用户解决平台使用过程中遇到的问题。

【平台知识库】
{SUPPORT_KNOWLEDGE}

【对话规则】
1. 优先使用知识库中的信息回答，确保准确性
2. 如果用户问题超出知识库范围，以通用助手身份礼貌回答，不要编造平台规则
3. 对于操作类问题，给出清晰的步骤指引
4. 如果用户表达不满或遇到报错，先安抚情绪，再提供解决方案
5. 保持回答简洁（100字以内），必要时可引导用户到具体页面操作
6. 如果用户连续追问同一问题，尝试换一种方式解释
7. 不要泄露系统内部技术细节（如API路径、数据库结构、密钥等）

【输出格式】
直接以自然语言回答，不要输出 JSON 或代码块格式。"""

# ---- 会话缓存（v1 对话记忆） ----
MAX_HISTORY = 10          # 保留最近 N 轮对话
SESSION_TTL_MINUTES = 30  # 会话过期时间

_support_sessions: dict[int, list[BaseMessage]] = {}
_session_last_active: dict[int, datetime] = {}
# ---- 状态机缓存（v2：每用户一个 SupportSessionState） ----
_support_states: dict[int, SupportSessionState] = {}


def _get_session(user_id: int) -> list[BaseMessage]:
    """获取或创建用户会话历史（v1 对话记忆）。"""
    now = datetime.now()
    last = _session_last_active.get(user_id)
    if last and (now - last) > timedelta(minutes=SESSION_TTL_MINUTES):
        _support_sessions.pop(user_id, None)
    _session_last_active[user_id] = now
    return _support_sessions.setdefault(user_id, [])


def _get_state(user_id: int) -> SupportSessionState:
    """获取或创建用户状态机实例（TTL 与对话记忆一致）。"""
    now = datetime.now()
    last = _session_last_active.get(user_id)
    if last and (now - last) > timedelta(minutes=SESSION_TTL_MINUTES):
        _support_states.pop(user_id, None)
    _session_last_active[user_id] = now
    return _support_states.setdefault(user_id, SupportSessionState())


def _trim_history(history: list[BaseMessage]) -> list[BaseMessage]:
    """保留最近 MAX_HISTORY 轮对话（每轮 = user + assistant）。"""
    if not history or MAX_HISTORY <= 0:
        return history
    base = [history[0]] if isinstance(history[0], SystemMessage) else []
    msgs = history[len(base):]
    # 找到所有轮次边界（AIMessage 位置），保留最后 MAX_HISTORY 轮
    ai_pos = [i for i, m in enumerate(msgs) if isinstance(m, AIMessage)]
    if len(ai_pos) <= MAX_HISTORY:
        return history
    cutoff = ai_pos[-MAX_HISTORY - 1] + 1
    return base + msgs[cutoff:]


# ==================== v2：工具绑定 ====================

def _bind_tools(state: SupportSessionState) -> dict[str, Callable]:
    """工具绑定：将纯函数工具绑定当前会话状态，返回「工具注册表」。

    与 Function Calling 工具集语义对齐（名字 + 输入输出契约），但调用时机由
    状态机决定（确定性分派）而非 LLM 自由调用，避免模型幻觉导致非法状态跳转。
    工具名是状态机与工具交互的唯一契约，后续可平滑替换为 llm.bind_tools 的
    完整 Function Calling 通道（扩展为 LLM 自主决策时保持不变）。
    """
    return {
        "analyze_goods_draft": partial(analyze_goods_draft, state),
        "generate_publish_payload": partial(generate_publish_payload, state),
        "confirm_publish": partial(confirm_publish, state),
        "cancel_task": partial(cancel_task, state),
        "reset_to_idle": partial(reset_to_idle, state),
    }


# ==================== v2：意图识别 ====================

# 强信号：直接触发发布任务
PUBLISH_STRONG_KEYWORDS = (
    "发布商品", "发布二手", "发布闲置", "我要卖", "卖东西", "出售",
    "转卖", "上架商品", "帮我把", "帮我发布", "帮我卖", "卖个",
    "卖台", "卖部", "卖一",
)
# 弱信号：需配合"卖/出 + 宾语"句型才触发
WEAK_PUBLISH_RE = re.compile(r"(?:卖|出售|出手|出掉)[\u4e00-\u9fa5a-zA-Z0-9]")
# 咨询型疑问（问"怎么发布"是咨询操作指引，不是发起任务）
# 匹配："怎么发布/如何发布/怎样发布/怎么卖/如何卖/发布商品需要什么/发布商品有什么要求" 等
HOW_TO_PUBLISH_RE = re.compile(
    r"(?:怎么|如何|怎样|咋|能不能|可以吗|需要什么|有什么要求|流程|步骤).{0,8}"
    r"(?:发布|卖|出售|上架|转卖)"
)


def _detect_publish_intent(question: str) -> bool:
    """检测用户是否想发起「发布商品」任务。

    强关键词直接命中；弱信号（卖/出 + 宾语）限定句型避免误判
    （如"这个二手平台怎么用"含"二手"但不触发）。
    咨询型疑问（"怎么发布二手商品？"）优先判定为非任务意图，走操作指引问答。
    """
    q = question.strip().lower()
    if HOW_TO_PUBLISH_RE.search(q):
        return False
    if any(k in q for k in PUBLISH_STRONG_KEYWORDS):
        return True
    if WEAK_PUBLISH_RE.search(q) and len(q) <= 40:
        return True
    return False


# 用户引导信号（收集阶段的可选触发词）
_TRIGGER_KEYS = ("分析", "开始分析", "识别", "帮我看看", "好了", "看看吧", "开始")

# 指令意图
_MODIFY_KEYS = ("修改", "重新", "不对", "错了", "再传", "补充", "换一个", "改一下", "重来")
_CANCEL_KEYS = ("取消", "算了", "放弃", "不要了", "不发了", "不想发布", "停")
_CONFIRM_KEYS = ("确认", "是的", "对的", "对", "可以", "没问题", "就这样", "好的", "好", "ok", "确定")


def _is_confirm(text: str) -> bool:
    if _is_modify(text) or _is_cancel(text):
        return False
    return any(k in text for k in _CONFIRM_KEYS)


def _is_modify(text: str) -> bool:
    return any(k in text for k in _MODIFY_KEYS)


def _is_cancel(text: str) -> bool:
    return any(k in text for k in _CANCEL_KEYS)


def _extract_hint(question: str) -> str:
    """从用户输入中提取商品描述 hint（排除指令/确认类文本）。"""
    q = question.strip()
    if not q:
        return ""
    if _is_confirm(q) or _is_modify(q) or _is_cancel(q):
        return ""
    if any(k in q for k in _TRIGGER_KEYS) and len(q) <= 12:
        return ""
    return q[:200]


# ==================== v2：状态机主流程 ====================

def _build_reply(
    state: SupportSessionState,
    answer: str,
    action: dict | None = None,
) -> dict:
    """构造结构化回复（前端据此渲染：文本 / 操作卡片 / 自动跳转）。"""
    return {
        "answer": answer,
        "task_state": state.task.value if state.task else TaskType.idle.value,
        "phase": state.phase.value if state.phase else None,
        "action": action,
    }


async def _handle_publish_goods(
    state: SupportSessionState,
    question: str,
    image_urls: list[str] | None,
) -> dict:
    """商品发布任务的状态机分派。

    阶段流转（can_transition 兜底，防非法跳转）：
    collecting_images -> awaiting_confirm（分析成功）-> awaiting_publish（确认分析）
    -> published（确认发布）；任意阶段可 -> cancelled；分析失败回退 collecting_images。
    """
    tools = _bind_tools(state)
    phase = state.phase

    # ---- 阶段1：收集图片/描述 ----
    if phase == PublishGoodsPhase.collecting_images:
        if _is_cancel(question):
            result_text = tools["cancel_task"](reason="收集阶段取消")
            return _build_reply(state, result_text)

        if image_urls:
            state.add_images([u for u in image_urls if u])
        hint = _extract_hint(question)
        if hint:
            state.set_user_hint(hint)

        # 已有图片：自动触发 AI 分析（除非之前已失败，避免死循环重试）
        if state.collected_images:
            if state.last_error:
                return _build_reply(
                    state,
                    f"[上次分析失败：{state.last_error}] 请更换清晰图片或补充商品描述后重新尝试。",
                )
            result_text = await tools["analyze_goods_draft"]()
            if state.phase == PublishGoodsPhase.awaiting_confirm:
                return _build_reply(
                    state, result_text,
                    action={"type": "analysis_confirm", "data": state.analysis_result},
                )
            # 分析失败：已自动回退 collecting_images，提示用户（last_error 已在工具内写入）
            return _build_reply(state, result_text)

        # 若用户只说了"分析"但没有图
        if any(k in question for k in _TRIGGER_KEYS):
            return _build_reply(
                state,
                "请先上传商品图片（最多6张），我才能帮你识别商品信息。也可以直接告诉我品牌型号、成色等信息。",
            )
        return _build_reply(
            state,
            "好的，我来帮你发布商品！请先上传商品图片（最多6张），也可以补充商品描述（如品牌、型号、成色）。",
        )

    # ---- 阶段2：等待确认分析结果 ----
    if phase == PublishGoodsPhase.awaiting_confirm:
        # 用户可能补图：回到收集阶段重新分析
        if image_urls:
            state.add_images([u for u in image_urls if u])
            state.phase = PublishGoodsPhase.collecting_images
            result_text = await tools["analyze_goods_draft"]()
            if state.phase == PublishGoodsPhase.awaiting_confirm:
                return _build_reply(
                    state, result_text,
                    action={"type": "analysis_confirm", "data": state.analysis_result},
                )
            return _build_reply(state, result_text)

        if _is_confirm(question):
            result_text = tools["generate_publish_payload"]()
            if state.phase == PublishGoodsPhase.awaiting_publish:
                return _build_reply(
                    state, result_text,
                    action={"type": "publish_confirm", "data": state.publish_payload},
                )
            return _build_reply(state, result_text)
        if _is_modify(question):
            if state.can_transition(PublishGoodsPhase.collecting_images):
                state.phase = PublishGoodsPhase.collecting_images
                return _build_reply(
                    state,
                    "好的，请修改或补充商品信息（品牌、型号、成色等），我会保留已上传图片并重新分析。",
                )
            return _build_reply(state, "当前状态无法修改，请取消后重新开始。")
        if _is_cancel(question):
            result_text = tools["cancel_task"](reason="确认前取消")
            return _build_reply(state, result_text)
        return _build_reply(
            state,
            "请确认以上商品信息是否正确？回复「确认」使用当前结果，「修改」重新分析，「取消」放弃本次发布。",
            action={"type": "analysis_confirm", "data": state.analysis_result},
        )

    # ---- 阶段3：等待确认正式发布 ----
    if phase == PublishGoodsPhase.awaiting_publish:
        if _is_confirm(question):
            result_text = tools["confirm_publish"]()
            return _build_reply(
                state, result_text,
                action={"type": "published", "data": state.publish_payload},
            )
        if _is_cancel(question):
            result_text = tools["cancel_task"](reason="用户取消发布")
            return _build_reply(state, result_text)
        if _is_modify(question):
            if state.can_transition(PublishGoodsPhase.awaiting_confirm):
                state.phase = PublishGoodsPhase.awaiting_confirm
                return _build_reply(state, "好的，回到信息确认环节，你可以再次确认或修改分析结果。")
            return _build_reply(state, "当前状态无法修改，请取消后重新开始。")
        return _build_reply(
            state,
            "请确认是否正式发布？回复「确认发布」完成，「取消」放弃，「修改」回到上一步。",
            action={"type": "publish_confirm", "data": state.publish_payload},
        )

    # ---- 已完成 / 已取消 / 未知阶段 ----
    return _build_reply(
        state,
        "你有一个新的需求吗？回复「我要发布商品」可以开始新的发布流程，或直接向我提问。",
    )


async def _general_chat(
    user_id: int,
    question: str,
    image_urls: list[str] | None = None,
) -> str:
    """v1 通用问答：嵌入式 RAG + 会话记忆（LLM 生成文本）。

    带图片时自动切换视觉模型（settings.LLM_VISION_MODEL）——文本模型收到
    image_url 内容块会直接报错或忽略，这是普通客服「看不见图」的根因。
    """
    history = _get_session(user_id)

    msgs: list[BaseMessage] = [SystemMessage(content=SUPPORT_SYSTEM)]
    if history:
        trimmed = _trim_history(history)
        for m in trimmed[1:]:
            msgs.append(m)
    _append_question_message(msgs, question, image_urls)
    use_vision = bool(image_urls)

    try:
        llm = _build_llm(settings.LLM_VISION_MODEL) if use_vision else _build_llm()
        raw = await llm.ainvoke(msgs)
        answer = _msg_text(raw)

        # 会话记忆只存文本：多模态内容体积大（base64），且重放给下一轮的文本模型会报错
        history.append(HumanMessage(content=question))
        history.append(AIMessage(content=answer))
        _session_last_active[user_id] = datetime.now()
        return answer
    except Exception as e:
        logger.error("support_agent general_chat failed for user=%s: %s", user_id, e)
        return "抱歉，我暂时遇到了一些问题，请稍后再试。如果问题持续，可以联系平台管理员。"


# ==================== v2：对外入口 ====================

async def agent_chat(
    user_id: int,
    question: str,
    image_urls: list[str] | None = None,
) -> dict:
    """结构化客服交互入口（v2，行动型）。

    流程：收图 -> 活跃任务优先走状态机 -> 无任务则意图识别 -> 普通问答降级。

    Returns:
        {
          "answer": str,            # AI 回复文本（前端直接展示）
          "task_state": str,        # idle / publish_goods ...
          "phase": str | None,      # 当前状态机阶段（collecting_images 等）
          "action": dict | None,    # 前端动作指令（analysis_confirm / publish_confirm / published）
        }
    """
    state = _get_state(user_id)

    # 1. 活跃任务：直接进入状态机
    if state.is_active_task:
        if state.task == TaskType.publish_goods:
            return await _handle_publish_goods(state, question, image_urls)
        return _build_reply(state, "当前任务暂不支持，已恢复为普通问答。")

    # 2. 发起新任务（意图识别）
    if _detect_publish_intent(question):
        state.start_publish_goods()
        return await _handle_publish_goods(state, question, image_urls)

    # 3. 普通问答降级
    answer = await _general_chat(user_id, question)
    return _build_reply(state, answer)


async def chat(user_id: int, question: str) -> str:
    """兼容 v1 接口：返回纯文本回答（API 旧端点 /support/chat 使用）。"""
    result = await agent_chat(user_id, question)
    return result["answer"]


def get_history(user_id: int) -> list[dict]:
    """获取用户会话历史（用于前端展示）。"""
    history = _get_session(user_id)
    result = []
    for m in history:
        if isinstance(m, HumanMessage):
            result.append({"role": "user", "content": _msg_text(m)})
        elif isinstance(m, AIMessage):
            result.append({"role": "assistant", "content": _msg_text(m)})
    return result


def clear_history(user_id: int) -> None:
    """清空用户会话历史与状态机。"""
    _support_sessions.pop(user_id, None)
    _session_last_active.pop(user_id, None)
    _support_states.pop(user_id, None)


# ==================== v3：SSE 流式输出 ====================

def _support_multimodal_content(image_urls: list[str], question: str) -> list[dict]:
    """构建普通客服对话的多模态消息内容（图片转 base64，视觉模型无需联网即可看图）。

    与 goods_agent._make_multimodal_content 的区别：那边是「生成商品发布 JSON」的
    专用提示词，这里是通用问答——文本部分就是用户原话，不做任务导向的改写。
    图片 base64 转换失败的会被静默跳过（goods_agent 的转换函数内部已记日志）。
    """
    content: list[dict] = []
    text = question.strip() or "请看这张图片，告诉我图片里有什么，以及平台能怎么帮我处理。"
    content.append({"type": "text", "text": text})
    for url in image_urls:
        if not url:
            continue
        data_url = _image_url_to_base64_dataurl(url)
        if data_url:
            content.append({"type": "image_url", "image_url": {"url": data_url}})
        else:
            logger.warning("客服对话图片转 base64 失败，已跳过: %s", url)
    return content


def _append_question_message(msgs: list[BaseMessage], question: str, image_urls: list[str] | None) -> None:
    """把用户本轮输入追加为 HumanMessage；带图片时构建多模态内容。

    返回值约定：调用方据此决定用文本模型还是视觉模型
    （见 _general_chat / _general_chat_stream 中的 `use_vision`）。
    """
    if image_urls:
        msgs.append(HumanMessage(content=_support_multimodal_content(image_urls, question)))
    else:
        msgs.append(HumanMessage(content=question))

async def _general_chat_stream(
    user_id: int,
    question: str,
    image_urls: list[str] | None = None,
) -> AsyncGenerator[dict, None]:
    """v1 通用问答流式版：流式生成 AI 回复文本，同时写入会话记忆。

    带图片时切换视觉模型（与 _general_chat 同一套逻辑）。
    """
    history = _get_session(user_id)

    msgs: list[BaseMessage] = [SystemMessage(content=SUPPORT_SYSTEM)]
    if history:
        trimmed = _trim_history(history)
        for m in trimmed[1:]:
            msgs.append(m)
    _append_question_message(msgs, question, image_urls)
    use_vision = bool(image_urls)

    full_answer = ""
    try:
        llm = _build_llm(settings.LLM_VISION_MODEL) if use_vision else _build_llm()
        async for chunk in llm.astream(msgs):
            text = _msg_text(chunk)
            if text:
                full_answer += text
                yield {"type": "delta", "text": text}

        # 会话记忆只存文本（同 _general_chat：base64 体积大且不能重放给文本模型）
        history.append(HumanMessage(content=question))
        history.append(AIMessage(content=full_answer))
        _session_last_active[user_id] = datetime.now()

        state = _get_state(user_id)
        yield {
            "type": "done",
            "answer": full_answer,
            "task_state": state.task.value if state.task else TaskType.idle.value,
            "phase": None,
            "action": None,
        }
    except Exception as e:
        logger.error("support_agent general_chat stream failed for user=%s: %s", user_id, e)
        yield {"type": "error", "text": "抱歉，我暂时遇到了一些问题，请稍后再试。如果问题持续，可以联系平台管理员。"}


async def _handle_publish_goods_stream(
    state: SupportSessionState,
    question: str,
    image_urls: list[str] | None,
) -> AsyncGenerator[dict, None]:
    """商品发布任务的流式包装器：复用原有状态机逻辑，按 SSE 事件分片推送。"""
    result = await _handle_publish_goods(state, question, image_urls)
    if result.get("answer"):
        yield {"type": "delta", "text": result["answer"]}
    yield {
        "type": "state",
        "task_state": result.get("task_state"),
        "phase": result.get("phase"),
        "action": result.get("action"),
    }
    yield {"type": "done", **result}


async def agent_chat_stream(
    user_id: int,
    question: str,
    image_urls: list[str] | None = None,
) -> AsyncGenerator[dict, None]:
    """流式客服交互入口（SSE）。

    Yields 事件类型：
        - delta  : {"type": "delta", "text": str}  文本增量（打字机效果）
        - state  : {"type": "state", "task_state": str, "phase": str|null, "action": dict|null}
        - done   : {"type": "done", "answer": str, "task_state": str, "phase": str|null, "action": dict|null}
        - error  : {"type": "error", "text": str}
    """
    state = _get_state(user_id)

    if state.is_active_task:
        if state.task == TaskType.publish_goods:
            async for event in _handle_publish_goods_stream(state, question, image_urls):
                yield event
            return
        yield {"type": "delta", "text": "当前任务暂不支持，已恢复为普通问答。"}
        yield {
            "type": "done",
            "answer": "当前任务暂不支持，已恢复为普通问答。",
            "task_state": state.task.value if state.task else TaskType.idle.value,
            "phase": None,
            "action": None,
        }
        return

    if _detect_publish_intent(question):
        state.start_publish_goods()
        async for event in _handle_publish_goods_stream(state, question, image_urls):
            yield event
        return

    async for event in _general_chat_stream(user_id, question, image_urls):
        yield event
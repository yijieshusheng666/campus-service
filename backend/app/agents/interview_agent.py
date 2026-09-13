"""AI 模拟面试 Agent：自研 ReAct 主循环（Thought → Action → Observation → Answer）。

设计要点（面试讲点）：
- 流式分流：循环内统一走 llm.astream，chunk 携带 tool_call_chunks → 工具轮（对前端静默），
  纯文本 chunk → 回答轮（文本增量逐段 yield，SSE delta 与改造前 UX 完全一致）；
- 防死循环：MAX_AGENT_ITERATIONS 硬上限 + 连续工具轮上限 + 空文本兜底，任何路径用户都能收到问题；
- 降级是代码路径：_bind_tools 失败（如 Ollama 原生协议不支持 tool calling）→ 单轮纯文本生成，与现状等价；
- 失败自纠错：工具执行异常不吞掉，作为 Observation 回喂模型，由模型修正参数或放弃工具。
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.interview_state import InterviewState
from app.agents.interview_tools import build_interview_tools
from app.services.interview_plan import format_plan_for_prompt, get_cached_plan
from app.services.llm import _bind_tools, _build_llm, _msg_text

logger = logging.getLogger(__name__)

# 单次提问迭代上限：达到上限不再给工具，强制生成问题文本
MAX_AGENT_ITERATIONS = 6
# 连续只调工具不产出文本的上限：防止模型陷入工具调用链
MAX_TOOL_ONLY_ROUNDS = 2
# 单个工具执行重试次数（总尝试 = retries + 1，指数退避 0.5s / 1s）
TOOL_RETRIES = 2
# 单条 Observation 回喂模型的最大字符数（防上下文膨胀）
MAX_OBSERVATION_CHARS = 2000
# system 中简历只注入索引片段，完整章节由 get_resume_section 按需取（上下文管理）
MAX_RESUME_INDEX_CHARS = 1500
# 上下文裁剪：最多携带最近 N 轮（与 interview.py 保持一致）
MAX_HISTORY_ROUNDS = 10

AGENT_SYSTEM = """你是一位资深的技术面试官，正在对候选人进行{job_position}岗位的模拟面试，当前面试阶段：{phase}。

【候选人简历（索引）】
{resume_text}
{plan_block}
【面试规则】
1. 每次只提出一个问题，基于简历内容与岗位要求，有针对性；问题之间绝不给评价或反馈
2. 提问难度递进：自我介绍开场（中等）→ 项目/经历深挖（深入）→ 技术基础 → 场景/开放题
3. 像真实面试官一样自适应追问：回答具体精彩 → 顺着细节往下深挖；回答含糊笼统 → 追问具体角色；
   出现"我们"式表述 → 要求拆出个人贡献；发现自相矛盾或惊人表述 → 当场追问，不要放过
4. 口吻专业、友好；不要一次抛出多个问题；不要输出与提问无关的内容

【提问槽位（每次提问落在以下九类之一，避免同一槽位连续重复）】
- 事实槽：你具体做了什么（如"这个项目里你实际动手写的是哪部分？"）
- 机制槽：为什么这么做、原理是什么
- 取舍槽：还有别的方案吗、为什么没选它
- 失败槽：出过什么问题、你是怎么定位到原因的
- 数字槽：多久、多大、多少（追问基数与口径）
- 协作槽：这件事谁决策的、分歧怎么对齐
- 迁移槽：换个场景或换一批数据，你的方案还成立吗
- 动机槽：为什么选这个方向与岗位
- 反思槽：现在回头看你会怎么改
深挖阶段优先事实槽+机制槽+数字槽；项目讨论交替使用取舍槽/失败槽/协作槽；收尾阶段才多用动机槽/迁移槽/反思槽。

【三层追问（同一锚点必须追到底，禁止问一层就换话题）】
第一层 澄清（消除模糊表述）→ 第二层 展开（定位个人贡献）→ 第三层 深挖（逼近机制与边界）
满足以下任一条件即换题：①已取得具体数字、机制解释、一次真实失败、明确取舍中的任一项；
②候选人连续两次答不出或明显回避（标记为"后续可补考"并降级换题，不要连环施压）；
③该锚点已追问三层且无新信息。

【反套路（防背稿与糊弄）】
- 用术语糊弄时：要求"用一句话讲给外专业的人听"
- 答得过于顺畅、高度模板化时：追问边界与反例（"这个方法什么场景下不成立？"）
- 引用团队成果时：追问个人动作与可验证细节（"具体哪部分是你写的？"）

【合规红线（优先于一切提问策略，触碰即替换为不越界的问法）】
- 严禁把性别、年龄、婚育状况、地域户籍、民族、院校出身、外貌、健康状况、家庭背景
  作为提问内容或评价依据
- 候选人主动提到上述话题时自然带过，不追问、不评价、不记为弱点
- 不臆造候选人没说过的事实；不承诺录用结果；不建议夸大或虚构经历

【你的工作方式（ReAct：Thought → Action → Observation → Answer）】
- 收到候选人回答后：先调用 evaluate_answer 快速评估，拿到追问信号（follow_up）与建议槽位；
  需要简历细节时调用 get_resume_section（如 projects / education / skills），不要假设简历全文可见；
  抛出问题前调用 check_question_asked 确认没有重复提问；判断信息已足够时调用 end_interview 输出收尾语。
- 最后一步永远是：直接输出下一个问题文本（这是你的 Answer，也是唯一对候选人可见的内容）。
"""


def _resume_index(resume_text: str) -> str:
    """简历索引：只注入开头片段（姓名/意向/首个章节），完整章节由工具按需取。"""
    text = (resume_text or "").strip()
    if not text:
        return "（未提供简历）"
    return text[:MAX_RESUME_INDEX_CHARS]


def _plan_block(resume_text: str) -> str:
    """取面试前分析并格式化为 system 片段；未命中缓存返回空串（不阻塞提问）。

    缓存由创建面试时的后台预热填充（见 services/interview_plan.py）。
    """
    try:
        plan = get_cached_plan(resume_text)
    except Exception:
        logger.exception("读取面试前分析失败（不影响面试）")
        return ""
    block = format_plan_for_prompt(plan)
    return f"\n{block}\n" if block else ""


def _infer_phase(state: InterviewState) -> str:
    """从对话轮数推断面试阶段（状态可从历史重建，不新增存储）。

    轮数阈值与 AGENT_SYSTEM 中"难度递进"节奏对齐：开场→深挖→技术→场景。
    """
    rounds = len(state.history) // 2  # 1 轮 = user + assistant
    if rounds < 2:
        return "opening"
    if rounds < 4:
        return "probing"
    if rounds < 7:
        return "technical"
    return "scenario"


def build_agent_messages(state: InterviewState) -> list:
    """构建 Agent 消息列表：system(岗位+简历索引+深挖计划+阶段+工具指引) + 最近 N 轮历史。

    history 元素形如 {"role": "user"|"assistant", "content": str}。
    """
    msgs: list = [
        SystemMessage(content=AGENT_SYSTEM.format(
            job_position=state.job_position or "AI应用开发",
            phase=_infer_phase(state),
            resume_text=_resume_index(state.resume_text),
            plan_block=_plan_block(state.resume_text),
        ))
    ]
    recent = state.history[-MAX_HISTORY_ROUNDS * 2:]
    for m in recent:
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        if m.get("role") == "user":
            msgs.append(HumanMessage(content=content))
        else:
            msgs.append(AIMessage(content=content))
    # OpenAI 兼容 API 要求 messages 必须含 user 消息，纯 system 数组报 1214
    if len(msgs) == 1:
        msgs.append(HumanMessage(content="请根据候选人的简历与目标岗位，开始第一轮提问。"))
    return msgs


def _parse_tool_args(args_json: str) -> dict:
    """解析工具参数 JSON；非法时原样包裹返回，供 Observation 回喂模型自纠错。"""
    try:
        data = json.loads(args_json or "{}")
        return data if isinstance(data, dict) else {"_raw": str(data)}
    except json.JSONDecodeError:
        return {"_raw": (args_json or "")[:500]}


async def _execute_tool_with_retry(tools: list, name: str, args_json: str) -> str:
    """执行工具并返回 Observation；失败重试后把错误作为 Observation 回喂模型。

    - 工具不存在：返回可用工具列表，引导模型修正；
    - 参数非 JSON 对象：返回错误提示（Pydantic 校验失败同样走此路径）；
    - 执行异常：指数退避重试 TOOL_RETRIES 次后把错误文本回喂模型。
    """
    tool = next((t for t in tools if t.name == name), None)
    if tool is None:
        return f"[工具不存在: {name}，可用工具: {', '.join(t.name for t in tools)}]"
    kwargs = _parse_tool_args(args_json)
    if not isinstance(kwargs, dict) or "_raw" in kwargs:
        return f"[工具参数必须是 JSON 对象，收到: {args_json[:200]}]"
    for attempt in range(TOOL_RETRIES + 1):
        try:
            result = await tool.ainvoke(kwargs)
            return str(result)[:MAX_OBSERVATION_CHARS]
        except Exception as e:
            if attempt >= TOOL_RETRIES:
                return f"[工具执行失败: {type(e).__name__}: {e}，请换一种方式处理]"
            await asyncio.sleep(0.5 * (2 ** attempt))  # 指数退避 0.5s / 1s
    return "[工具不可用]"


async def _plain_question(state: InterviewState) -> AsyncGenerator[str, None]:
    """去工具兜底：纯 LLM 单轮生成问题（降级路径与超限兜底共用，保证用户必能收到问题）。"""
    msgs = build_agent_messages(state)
    llm = _build_llm()
    async for chunk in llm.astream(msgs):
        if text := _msg_text(chunk):
            yield text


async def agent_stream_question(state: InterviewState) -> AsyncGenerator[str, None]:
    """ReAct 主循环：流式产出面试官的下一个问题。

    工具轮（模型声明工具调用）对前端静默；回答轮（纯文本）文本增量逐段 yield。
    任一失败路径最终都会落回 _plain_question，保证调用方总能流式收到一个问题。
    """
    tools = build_interview_tools(state)
    llm = _build_llm()
    bound, ok = _bind_tools(llm, tools)
    if not ok:
        # 降级是代码路径：不支持工具调用的模型（Ollama 原生协议）走单轮纯文本
        async for text in _plain_question(state):
            yield text
        return

    messages = build_agent_messages(state)
    tool_only_rounds, iterations = 0, 0
    while iterations < MAX_AGENT_ITERATIONS:
        iterations += 1
        calls: dict[int, dict] = {}
        text_parts: list[str] = []
        async for chunk in bound.astream(messages):
            tcs = getattr(chunk, "tool_call_chunks", None)
            if tcs:
                for tc in tcs:
                    index = tc.get("index") if tc.get("index") is not None else len(calls)
                    slot = calls.setdefault(index, {"name": "", "args": "", "id": ""})
                    slot["name"] += tc.get("name") or ""
                    slot["args"] += tc.get("args") or ""
                    slot["id"] = tc.get("id") or slot["id"]
            else:
                if text := _msg_text(chunk):  # 回答轮：流式输出（与现状 delta 行为一致）
                    text_parts.append(text)
                    yield text

        state.iteration_total += 1
        if not calls:
            answer = "".join(text_parts).strip()
            if not answer:  # 空文本兜底
                async for text in _plain_question(state):
                    yield text
            return  # 有文本则已逐段 yield

        tool_only_rounds += 1
        if tool_only_rounds > MAX_TOOL_ONLY_ROUNDS:  # 连续只调工具 → 强制收尾
            break

        for index in sorted(calls):
            call = calls[index]
            call_id = call.get("id") or f"call_{uuid.uuid4().hex[:12]}"
            obs = await _execute_tool_with_retry(tools, call["name"], call["args"])
            # 工具内部已自记录 trace（note_tool），这里只回填 LLM 消息
            messages.append(AIMessage(
                content="",
                tool_calls=[{"name": call["name"], "args": _parse_tool_args(call["args"]), "id": call_id}],
            ))
            messages.append(ToolMessage(content=obs, tool_call_id=call_id))
            logger.info("agent trace: tool=%s args=%s obs=%s",
                        call["name"], call["args"][:120], obs[:120])

    # 达到迭代上限：不再给工具，强制生成问题文本
    async for text in _plain_question(state):
        yield text
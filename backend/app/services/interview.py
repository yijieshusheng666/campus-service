"""AI 模拟面试服务：面试官流式提问 + 结束评估报告。

复用 app/services/llm.py 的 LLM 客户端构建与稳健 JSON 解析；
提问走 app/agents/interview_agent.py 的 ReAct 主循环（工具轮静默、回答轮流式，
SSE 事件契约与改造前完全一致；不支持工具调用的模型自动降级纯文本）。
"""
import logging
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.interview_agent import agent_stream_question
from app.agents.interview_state import InterviewState
from app.services.llm import _build_llm, _msg_text, _robust_json_parse

logger = logging.getLogger(__name__)

# 上下文裁剪：最多携带最近 N 轮（1 轮 = user + assistant）
MAX_HISTORY_ROUNDS = 10

INTERVIEWER_SYSTEM = """你是一位资深的技术面试官，正在对候选人进行{job_position}岗位的模拟面试。

【候选人简历】
{resume_text}

【面试规则】
1. 每次只提出一个问题，基于简历内容与岗位要求，有针对性；问题之间绝不给评价或反馈（模拟真实面试，评估在结束后的报告环节进行）
2. 提问难度递进：自我介绍开场（中等）→ 项目/经历深挖（深入）→ 技术基础 → 场景/开放题（可含一道有压力的追问）
3. 像真实面试官一样自适应追问：
   - 回答具体精彩 → 顺着最有趣的细节往下深挖（如"为什么选X而不是Y？"）
   - 回答含糊笼统 → 追问具体角色（如"这里面你个人具体负责什么？"）
   - 出现"我们"式表述 → 要求拆出个人贡献
   - 发现自相矛盾或惊人表述 → 当场追问，不要放过
4. 追问要深入：技术选型原因、量化数据来源、STAR 各环节展开、踩坑与解决
5. 口吻专业、友好；不要一次抛出多个问题；不要输出与提问无关的内容
"""

REPORT_SYSTEM = """你是资深面试教练，基于一场完整的模拟面试记录输出教练式评估报告（debrief）。
评估使用五维量规（每维 1-5 分），并按应届生/校招（0-3 年）标准校准：4 分=具体例子+至少一个量化数字；差异化可来自学习速度与求知欲。

五维定义：
- substance（实质证据）：证据质量与深度。1=空泛口号无证据；3=具体但未量化；5=量化+备选方案权衡+决策依据+结果
- structure（叙事结构）：1=意识流无重点；3=有结构但衔接生硬；5=铺垫→冲突→解决→影响，句句推进
- relevance（切题聚焦）：1=答非所问；3=切题但有无关细节；5=句句服务于回答
- credibility（可信度）：1=夸大无支撑；3=细节具体但缺结果；5=数字+佐证+他人认可+真实约束
- differentiation（差异化）：1=任何人都能说的答案；3=有细节但无独到洞察；5=只有这位候选人才能给出的经验与观点

**只返回紧凑JSON（不要任何解释、markdown、多余换行缩进）**。

JSON结构（字段名不要改）：
{"overall_score": 0到100整数, "hire_signal": "strong_hire|hire|mixed|no_hire", "summary": "一句话：这场面试会给面试官留下什么整体印象", "dimensions": [{"name": "substance|structure|relevance|credibility|differentiation", "score": 1到5整数, "comment": "证据化评价，必须引用候选人原话"}], "per_question": [{"index": 从1开始的序号, "question": "面试官问题摘要", "scores": {"substance": 1到5, "structure": 1到5, "relevance": 1到5, "credibility": 1到5, "differentiation": 1到5}, "strongest": "这题回答中最强的时刻", "missed": "错失的机会"}], "patterns": {"crutch_phrases": ["反复出现的口头禅/套路表述"], "avoided_topics": ["回避或绕开的话题"], "best_moment": "全场最佳时刻（引用原话）", "worst_moment": "最弱时刻及当时表现"}, "top_changes": ["下一场面试最该改的3件事，具体可执行"]}

要求：
1. hire_signal 按整体表现定级：strong_hire=多维度4-5分且展现独特价值；hire=多数3-4分、短板可辅导；mixed=表现不稳定；no_hire=多维度低分或证据严重不足
2. dimensions 五维分数按整场综合表现给出；comment 必须引用候选人原话作为证据，禁止空泛评价
3. per_question 覆盖每一轮候选人回答（面试官的提问不算）；strongest/missed 要具体
4. top_changes 恰好 3 条，按影响力排序，针对本场暴露的最大短板给出可执行的改法（如何练、改什么）
5. 所有内容使用中文
"""


def build_interview_messages(
    resume_text: str, job_position: str, history: list[dict]
) -> list:
    """构建 LLM 消息列表：system(简历+岗位) + 最近 N 轮历史。

    history 元素形如 {"role": "user"|"assistant", "content": str}。
    """
    msgs: list = [
        SystemMessage(content=INTERVIEWER_SYSTEM.format(
            job_position=job_position, resume_text=resume_text[:8000] or "（未提供简历）"
        ))
    ]
    recent = history[-MAX_HISTORY_ROUNDS * 2:]
    for m in recent:
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        if m.get("role") == "user":
            msgs.append(HumanMessage(content=content))
        else:
            msgs.append(AIMessage(content=content))
    # 智谱等 OpenAI 兼容 API 要求 messages 必须含 user 消息，纯 system 数组报 1214
    if len(msgs) == 1:
        msgs.append(HumanMessage(content="请根据候选人的简历与目标岗位，开始第一轮提问。"))
    return msgs


def _rebuild_state(resume_text: str, job_position: str, history: list[dict]) -> InterviewState:
    """从 API 入参重建 InterviewState：历史 assistant 消息即已问问题（可重建，不新增库表）。"""
    state = InterviewState.from_request(
        resume_text=resume_text, job_position=job_position, history=history
    )
    for m in history:
        if isinstance(m, dict) and m.get("role") == "assistant":
            state.add_asked_question(str(m.get("content", "")))
    return state


async def stream_question(
    resume_text: str, job_position: str, history: list[dict]
) -> AsyncGenerator[str, None]:
    """流式生成面试官的下一个问题（逐段 yield 文本增量）。

    委托 Agent ReAct 主循环：工具轮对前端静默、回答轮文本增量逐段 yield；
    模型/后端不支持工具调用时自动降级为纯文本生成（与改造前行为等价）。
    SSE 事件契约（start/delta/done/error）与前端消费方式完全不变。
    """
    state = _rebuild_state(resume_text, job_position, history)
    async for text in agent_stream_question(state):
        yield text


async def generate_report(
    resume_text: str, job_position: str, history: list[dict]
) -> dict:
    """生成评估报告 dict，失败返回空 dict。"""
    llm = _build_llm()
    transcript = "\n\n".join(
        f"{'候选人' if m.get('role') == 'user' else '面试官'}：{m.get('content', '')}"
        for m in history
    )
    msgs = [
        SystemMessage(content=REPORT_SYSTEM),
        HumanMessage(
            content=(
                f"【目标岗位】{job_position}\n\n"
                f"【候选人简历】\n{resume_text[:6000] or '（未提供）'}\n\n"
                f"【面试记录】\n{transcript[:12000]}"
            )
        ),
    ]
    try:
        raw = await llm.ainvoke(msgs)
        text = _msg_text(raw)
        report = _robust_json_parse(text)
        if not report or "overall_score" not in report:
            logger.warning("评估报告解析失败，原文起始: %s", str(text)[:300])
            return {}
        # 教练式报告字段兜底：缺失时给默认值，前端按字段是否存在区分新旧报告
        report.setdefault("hire_signal", "")
        report.setdefault("summary", "")
        report.setdefault("dimensions", [])
        report.setdefault("per_question", [])
        report.setdefault("patterns", {})
        report.setdefault("top_changes", [])
        return report
    except Exception:
        logger.exception("评估报告生成失败")
        return {}

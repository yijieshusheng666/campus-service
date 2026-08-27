"""AI 模拟面试服务：面试官流式提问 + 结束评估报告。

复用 app/services/llm.py 的 LLM 客户端构建与稳健 JSON 解析。
"""
import logging
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.llm import _build_llm, _robust_json_parse

logger = logging.getLogger(__name__)

# 上下文裁剪：最多携带最近 N 轮（1 轮 = user + assistant）
MAX_HISTORY_ROUNDS = 10

INTERVIEWER_SYSTEM = """你是一位资深的技术面试官，正在对候选人进行{job_position}岗位的模拟面试。

【候选人简历】
{resume_text}

【面试规则】
1. 每次只提出一个问题，问题要基于简历内容与岗位要求，有针对性
2. 提问顺序参考真实面试：自我介绍开场 → 项目/经历深挖 → 技术基础 → 场景/开放题
3. 追问要深入：技术选型原因、量化数据来源、STAR 各环节展开、踩坑与解决
4. 口吻专业、友好；不要一次抛出多个问题；不要输出与提问无关的内容
5. 不评价候选人的回答（评价在面试结束的评估报告环节进行）
"""

REPORT_SYSTEM = """你是资深面试官与职业教练，基于一场完整的模拟面试记录输出评估报告。
**只返回紧凑JSON（不要任何解释、markdown、多余换行缩进）**。

JSON结构（字段名不要改）：
{{"overall_score": 0到100整数, "dimensions": [{{"name": "维度名", "score": 0到100整数, "comment": "一句话评价"}}], "strengths": ["优势点", "..."], "weaknesses": ["短板", "..."], "suggestions": ["具体可执行的改进建议", "..."]}}

评估维度建议（可按实际内容取舍4-6个）：简历质量与岗位匹配度、项目深度与技术功底、表达逻辑与结构化、量化意识、技术基础、应变能力。
要求：strengths/weaknesses/suggestions 各 2-4 条，必须引用面试中的具体内容，禁止空泛套话；不得编造面试中未出现的信息。所有内容使用中文。
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
        content = str(m.get("content", ""))
        if m.get("role") == "user":
            msgs.append(HumanMessage(content=content))
        else:
            msgs.append(AIMessage(content=content))
    return msgs


async def stream_question(
    resume_text: str, job_position: str, history: list[dict]
) -> AsyncGenerator[str, None]:
    """流式生成面试官的下一个问题（逐段 yield 文本增量）。"""
    llm = _build_llm()
    msgs = build_interview_messages(resume_text, job_position, history)
    async for chunk in llm.astream(msgs):
        text = getattr(chunk, "text", "")
        if text:
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
        text = raw.text if hasattr(raw, "text") else str(raw)
        report = _robust_json_parse(text)
        if not report or "overall_score" not in report:
            logger.warning("评估报告解析失败，原文起始: %s", str(text)[:300])
            return {}
        return report
    except Exception:
        logger.exception("评估报告生成失败")
        return {}

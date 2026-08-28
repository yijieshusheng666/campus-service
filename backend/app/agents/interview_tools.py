"""面试官 Agent 的工具集：只读、无副作用、失败可恢复。

阶段一提供两个工具：
- get_resume_section：按需获取简历章节，避免把整份简历塞进上下文（上下文管理）；
- evaluate_answer：对候选人最新回答做四维快速评估，输出追问策略信号（感知层）。

工具通过 build_interview_tools(state) 闭包绑定会话状态，保持 @tool 入参/出参
为纯字符串契约，便于 schema 生成与序列化。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from app.agents.interview_state import (
    MAX_RESUME_SECTION_CHARS,
    VALID_SECTIONS,
    InterviewState,
    normalize_question,
)
from app.config import settings
from app.services.llm import _build_llm, _robust_json_parse

logger = logging.getLogger(__name__)

# 简历章节：英文枚举 -> 中文标题关键词（用于把 "## 教育经历" 这类标题归入枚举）
SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "education": ("教育", "学校", "学历", "education"),
    "skills": ("技能", "专业能力", "skills"),
    "experience": ("实习", "工作", "经历", "experience"),
    "projects": ("项目", "projects"),
    "summary": ("自我评价", "个人介绍", "个人简介", "summary"),
}

# ---- evaluate_answer 常量 ----

# 回答少于该字数不做 LLM 评估（信息量不足以产生可靠信号）
MIN_EVAL_CHARS = 200
# 输入评估的回答最多保留的字符数（截断防超长）
EVAL_MAX_CHARS = 2000

# 追问策略信号枚举
FOLLOW_UP_OPTIONS = (
    "deepen_project",
    "clarify_role",
    "probe_contradiction",
    "check_knowledge",
    "move_on",
)

# ---- check_question_asked 常量 ----

# 字符集合 Jaccard 相似度阈值：≥该值判断为重复提问
# 中文无天然分词，按字符集合近似词集合 Jaccard（不引入 jieba 等分词依赖）
CHECK_SIMILARITY_THRESHOLD = 0.6

# ---- end_interview 常量 ----

# 收尾语缓存在 tool_cache 的键（幂等：重复调用返回同一收尾，不重复生成）
CLOSING_CACHE_KEY = "_closing_summary"

DEFAULT_CLOSING = "今天的面试到这里就结束了。你可以点击「结束面试」，我会为你生成完整的评估报告。"

EVAL_SYSTEM = """你是资深技术面试官的评估助手，负责对候选人刚给出的面试回答做**快速评估**，辅助面试官决定如何追问。只返回紧凑JSON（不要任何解释、不要markdown、不要多余换行缩进）。

JSON结构（字段名不要改）：
{"substance": 1到3整数, "structure": 1到3整数, "clarity": 1到3整数, "depth": 1到3整数, "evidence": "一句话证据（引用回答原文要点）", "follow_up": "追问策略信号"}

维度定义（尽量苛刻：4分及以上才值得深挖，多数应届生回答集中在2-3分）：
- substance（实质证据）：回答里有多少具体事实、量化数字、技术细节。1=空泛口号；2=有细节但无量化；3=有量化+权衡+结果
- structure（叙事结构）：1=意识流无重点；2=有结构但衔接生硬；3=铺垫→冲突→解决→影响
- clarity（表达清晰）：1=含糊笼统；2=清楚但有冗余；3=简洁准确
- depth（思考深度）：1=停留表面；2=有一定思考；3=有取舍权衡与反思

follow_up 只能取以下枚举之一：
- deepen_project：回答具体精彩，值得顺着细节深挖（追问"为什么选X而不是Y"）
- clarify_role：表述含糊或出现"我们/团队"，需要拆出个人贡献
- probe_contradiction：发现自相矛盾或惊人表述，需要当面追问
- check_knowledge：回答偏乏力，需要回到技术基础或场景题验证
- move_on：信息已充分或该话题意义不大，建议换话题

应届生/校招（0-3年）校准：substance=3 必须含至少一个量化数字；clarity=3 不要求深度但必须聚焦。所有内容使用中文。"""


def _slice_resume(resume_text: str, section: str) -> str:
    """按 "## 标题" 结构切出简历指定章节，返回不超过 MAX_RESUME_SECTION_CHARS 的片段。

    匹配规则：标题文本包含该枚举任一关键词即命中（兼容"教育经历/项目经验"等中文标题）。
    """
    if not resume_text.strip():
        return "[简历为空，无法获取章节]"
    parts = re.split(r"\n##\s*", resume_text)
    keywords = SECTION_KEYWORDS.get(section, ())
    for part in parts[1:]:  # part[0] 是"姓名/求职意向"首部，无章标题
        title = part.splitlines()[0].strip() if part else ""
        if any(kw in title for kw in keywords):
            return part[:MAX_RESUME_SECTION_CHARS]
    return f"[未找到章节 {section}，可用章节: {', '.join(sorted(VALID_SECTIONS))}]"


def build_get_resume_section(state: InterviewState):
    """构造 get_resume_section 工具（闭包绑定会话状态与章节缓存）。"""

    @tool
    def get_resume_section(section: str) -> str:
        """按需获取候选人简历指定章节的内容，避免把整份简历塞进上下文。

        合法章节：education / skills / experience / projects / summary。
        返回该章节的文本片段（最多 1500 字）；章节不存在时返回可用章节列表。
        """
        section = (section or "").strip().lower()
        if section not in VALID_SECTIONS:
            return f"[非法章节 {section}，可用章节: {', '.join(sorted(VALID_SECTIONS))}]"
        cached = state.tool_cache.get(section)
        if cached is not None:
            return cached
        text = _slice_resume(state.resume_text, section)
        state.tool_cache[section] = text
        state.note_tool("get_resume_section", section, f"chars={len(text)}")
        return text

    return get_resume_section


# ---- evaluate_answer ----

def _neutral_eval_json(reason: str) -> str:
    """构造中性评估（系统不可用/输入不足时兜底，避免工具调用失败破坏主流程）。"""
    return json.dumps(
        {
            "substance": 2,
            "structure": 2,
            "clarity": 2,
            "depth": 2,
            "evidence": reason,
            "follow_up": "move_on",
        },
        ensure_ascii=False,
    )


def _sanitize_eval(data: dict) -> dict:
    """钳制 LLM 评估输出到合法范围，缺字段给默认值。"""
    def clamp_score(v: Any) -> int:
        try:
            n = int(v)
        except (TypeError, ValueError):
            return 2
        return min(3, max(1, n))

    follow_up = str(data.get("follow_up", "move_on") or "move_on").strip()
    if follow_up not in FOLLOW_UP_OPTIONS:
        follow_up = "move_on"
    return {
        "substance": clamp_score(data.get("substance")),
        "structure": clamp_score(data.get("structure")),
        "clarity": clamp_score(data.get("clarity")),
        "depth": clamp_score(data.get("depth")),
        "evidence": str(data.get("evidence") or "")[:200],
        "follow_up": follow_up,
    }


def _evaluate_with_llm(answer: str) -> dict:
    """单次非流式评估调用，返回四维评分与追问信号字典。"""
    prompt = ChatPromptTemplate.from_messages(
        [SystemMessage(content=EVAL_SYSTEM), ("human", "{answer}")]
    )
    llm = _build_llm()
    # JSON 模式仅对 OpenAI 兼容客户端生效；Ollama 原生协议不支持则跳过
    from langchain_openai import ChatOpenAI

    if isinstance(llm, ChatOpenAI):
        llm = llm.bind(response_format={"type": "json_object"})
    chain = prompt | llm | StrOutputParser()
    raw = chain.invoke({"answer": answer})
    parsed = _robust_json_parse(raw)
    if not parsed:
        logger.warning("evaluate_answer 输出无法解析为 JSON，按中性处理")
        return _sanitize_eval({})
    return _sanitize_eval(parsed)


def build_evaluate_answer(state: InterviewState):
    """构造 evaluate_answer 工具（闭包绑定会话状态）。"""

    @tool
    def evaluate_answer(candidate_answer: str) -> str:
        """快速评估候选人刚给出的回答的四维质量，并给出追问策略信号。

        返回 JSON：substance/structure/clarity/depth（1-3 分）+ evidence + follow_up
        （deepen_project / clarify_role / probe_contradiction / check_knowledge / move_on）。
        回答不足 200 字时不调用 LLM，返回中性评估。
        """
        answer = (candidate_answer or "").strip()
        if len(answer) < MIN_EVAL_CHARS:
            return _neutral_eval_json("回答过短（不足200字），无法可靠评估，建议先澄清")
        if len(answer) > EVAL_MAX_CHARS:
            answer = answer[:EVAL_MAX_CHARS]
        try:
            result = _evaluate_with_llm(answer)
        except Exception as e:
            logger.warning("evaluate_answer 调用失败: %s", e)
            return _neutral_eval_json("评估暂时不可用，按中性处理")
        state.note_tool("evaluate_answer", f"chars={len(answer)}",
                        f"follow_up={result['follow_up']}")
        return json.dumps(result, ensure_ascii=False)

    return evaluate_answer


# ---- check_question_asked ----

def _char_jaccard(a: str, b: str) -> float:
    """字符集合 Jaccard 相似度（中文按字符近似词集合，不引入分词依赖）。

    两段文本字符集合重合度：|A∩B| / |A∪B|；空集对返回 0。
    """
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _similar_question_text(state: InterviewState, normalized: str) -> str:
    """在历史 assistant 消息中找回与归一化问题对应的原文（Observation 提示模型换角度）。

    找不到原文时回退到归一化文本本身，保证 similar 字段永远有内容。
    """
    if not normalized:
        return ""
    for m in state.history:
        if m.get("role") != "assistant":
            continue
        content = str(m.get("content", "") or "").strip()
        if content and normalize_question(content) == normalized:
            return content[:200]
    return normalized[:200]


def build_check_question_asked(state: InterviewState):
    """构造 check_question_asked 工具（闭包绑定已问问题列表）。

    多轮（10+）后模型容易重复提问；本工具在提问前查重：
    归一化 + 字符 Jaccard 相似度（阈值 CHECK_SIMILARITY_THRESHOLD）判断重复，
    重复时 Observation 携带最近相似问题原文，模型据此换角度追问。
    """

    @tool
    def check_question_asked(question: str) -> str:
        """检查将要提出的问题是否与已问问题重复。

        返回 JSON：{"duplicated": bool, "similar": "最相似的历史问题原文(可为空)",
        "similarity": 0-1相似度, "advice": "提示"}。
        重复时换一个角度/不同维度提问；空文本视为不重复。
        """
        question = (question or "").strip()
        if not question:
            return json.dumps(
                {"duplicated": False, "similar": "", "similarity": 0.0, "advice": "空文本，视为不重复"},
                ensure_ascii=False,
            )
        normalized = normalize_question(question)
        if not normalized:
            return json.dumps(
                {"duplicated": False, "similar": "", "similarity": 0.0, "advice": "无可比较内容，视为不重复"},
                ensure_ascii=False,
            )
        best_prev, best_sim = "", 0.0
        for prev in state.asked_questions:
            sim = _char_jaccard(normalized, prev)
            if sim > best_sim:
                best_prev, best_sim = prev, sim
        duplicated = best_sim >= CHECK_SIMILARITY_THRESHOLD
        similar_text = _similar_question_text(state, best_prev) if duplicated and best_prev else ""
        result = {
            "duplicated": duplicated,
            "similar": similar_text,
            "similarity": round(best_sim, 2),
            "advice": "该问题与已问问题重复，请换一个角度或更深的维度追问" if duplicated else "未重复，可以提问",
        }
        state.note_tool("check_question_asked", question[:100],
                        f"duplicated={duplicated}, sim={best_sim:.2f}")
        return json.dumps(result, ensure_ascii=False)

    return check_question_asked


# ---- end_interview ----

def build_end_interview(state: InterviewState):
    """构造 end_interview 工具（闭包绑定收尾语缓存）。

    v1 渐进版：结束仍由用户点击 finish 触发，工具只输出自然收尾语
    （复用 delta/done 通道，前端无需改动）；幂等：重复调用返回同一收尾。
    """

    @tool
    def end_interview(closing_summary: str) -> str:
        """信息收集已充分，输出收尾语结束面试。

        返回给候选人的自然收尾语（含点击「结束面试」生成评估报告的引导）。
        幂等：会话内重复调用返回同一句收尾。
        """
        cached = state.tool_cache.get(CLOSING_CACHE_KEY)
        if cached:
            return cached
        text = (closing_summary or "").strip()
        if not text or len(text) > 200:
            text = text[:200] if text else DEFAULT_CLOSING
        state.tool_cache[CLOSING_CACHE_KEY] = text
        state.note_tool("end_interview", f"chars={len(text)}", "closing")
        return text

    return end_interview


def build_interview_tools(state: InterviewState) -> list:
    """阶段二工具集：get_resume_section + evaluate_answer + check_question_asked + end_interview。"""
    return [
        build_get_resume_section(state),
        build_evaluate_answer(state),
        build_check_question_asked(state),
        build_end_interview(state),
    ]
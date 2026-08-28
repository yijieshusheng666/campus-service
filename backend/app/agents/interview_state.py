"""InterviewState：AI 模拟面试 Agent 的会话级状态。

- 可重建：history / asked_questions 可由数据库 messages 推导；
- 会话瞬态：tool_cache（章节切片缓存）与 last_trace（决策轨迹）只活在进程内；
- 不新增数据库表：状态由 API 入参构造，会话结束后可弃。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 简历章节白名单（get_resume_section 只接受这些枚举）
VALID_SECTIONS = frozenset({"education", "skills", "experience", "projects", "summary"})

# 章节切片返回的最大字符数
MAX_RESUME_SECTION_CHARS = 1500

# 面试阶段状态机（v1 由外部提示注入；v2 由工具推进）
PHASES = ("opening", "probing", "technical", "scenario", "closing")


def normalize_question(question: str) -> str:
    """把提问归一化为可比较的形式：去标点空白、小写化，供查重使用。

    归一化只保留中文/英文/数字，其余字符一律去掉。
    """
    text = (question or "").strip()
    if not text:
        return ""
    text = re.sub(r"[^\w\u4e00-\u9fff]", "", text, flags=re.UNICODE)
    return text.lower()


@dataclass
class InterviewState:
    resume_text: str = ""
    job_position: str = ""
    history: list[dict] = field(default_factory=list)
    asked_questions: list[str] = field(default_factory=list)
    tool_cache: dict[str, str] = field(default_factory=dict)
    phase: str = "opening"
    iteration_total: int = 0
    last_trace: list[dict] = field(default_factory=list)

    @classmethod
    def from_request(
        cls,
        resume_text: str = "",
        job_position: str = "",
        history: list[dict] | None = None,
    ) -> "InterviewState":
        """从 API 入参构造状态（见 api/interviews.py 的 chat 流程）。

        history 与 models.interview.InterviewMessage 同构：[
            {"role": "assistant" | "user", "content": "..."}
        ]
        """
        return cls(
            resume_text=resume_text or "",
            job_position=job_position or "",
            history=list(history or []),
        )

    def add_asked_question(self, question: str) -> None:
        """记录一条已问问题（归一化后去重追加）。"""
        normalized = normalize_question(question)
        if normalized and normalized not in self.asked_questions:
            self.asked_questions.append(normalized)

    def note_tool(self, name: str, args: str, result_summary: str) -> None:
        """记录一次工具调用轨迹（供评测与回放；阶段二 trace 落日志）。

        iteration_total 由 ReAct 主循环统一递增（语义 = 主循环迭代轮数），
        工具自身不参与迭代计数，避免双重计数。
        """
        self.last_trace.append(
            {"name": name, "args": args, "result": result_summary[:200]}
        )
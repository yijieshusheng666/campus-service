"""面试前简历分析（深挖计划）的缓存与提示词格式化。

借鉴 campus-interviewer 的 resume-parsing.md + interviewer-engine.md：
面试开始前对简历做一次性分析（形态判定 → 深挖清单 → 风险信号 → 开场亮点题），
面试官据此提问，而不是每轮临时现找。

**为什么需要缓存**：InterviewState 每轮请求都由 API 入参重建（见 interview_state.py
的设计约束），若在构建 system 时同步分析简历，会话每轮都会多出一次 LLM 往返。
因此这里做进程内缓存：创建面试时后台预热一次，之后各轮只读缓存。

**为什么单独成文件**：agents/interview_agent.py 需要读取本缓存，而该模块已被
services/interview.py 导入；把缓存放在 services/interview.py 会造成循环导入。

降级原则：缓存未命中时返回 None，面试官按「无分析」正常提问，不阻塞、不报错。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging

from app.services.llm import analyze_resume_for_interview

logger = logging.getLogger(__name__)

# key = 简历文本 sha1 -> 分析结果 dict
_PLAN_CACHE: dict[str, dict] = {}
# 正在分析中的 key：避免同一份简历并发重复分析（如用户连点两次创建）
_PLAN_INFLIGHT: set[str] = set()
# 缓存条目上限：简历文本较长，超限时整体清空（增量极低频，无需 LRU 复杂度）
_MAX_CACHE_ENTRIES = 64

# 预热失败重试（如免费模型高峰期 429 限流）：深挖计划是面试质量的关键输入，
# 后台任务多等几十秒换取计划就绪，比整场面试没有计划划算。间隔为秒。
_PREWARM_RETRIES = 2
_PREWARM_BACKOFF = (5.0, 15.0)

# 简历形态枚举 -> 中文（注入 prompt 用中文，便于模型理解与引用）
PROFILE_LABELS = {
    "no_internship": "无实习型",
    "pure_campus": "纯校园经历型",
    "cross_major": "跨专业转行型",
    "weak_school": "学历背景较弱型",
    "research": "科研论文型",
    "multi_short_intern": "多段短实习型",
    "single_long": "单段长经历型",
    "startup": "创业自由职业型",
    "non_tech": "非技术岗",
    "gap": "经历明显空白型",
}

# 追问动作枚举 -> 中文
PATH_LABELS = {
    "clarify": "澄清模糊表述",
    "expand": "定位个人贡献",
    "dig": "逼近机制与边界",
    "number": "追问数字口径",
    "tradeoff": "追问其他方案与取舍",
    "failure": "追问踩坑与定位过程",
}


def plan_key(resume_text: str) -> str:
    """简历文本的缓存键（内容相同即复用同一份分析）。"""
    return hashlib.sha1((resume_text or "").encode("utf-8")).hexdigest()


def get_cached_plan(resume_text: str) -> dict | None:
    """只读缓存：命中返回深挖计划，未命中返回 None。

    本函数**绝不触发 LLM 调用**——构建 system 的路径上不能有阻塞调用。
    """
    if not resume_text:
        return None
    return _PLAN_CACHE.get(plan_key(resume_text))


async def prewarm_plan(resume_text: str) -> None:
    """后台预热面试前分析（创建面试时调用）。

    失败（含 429 限流）时按 _PREWARM_BACKOFF 重试；最终仍失败只记日志——
    没有深挖计划时面试照常进行（面试官退回自由发挥），不阻塞、不报错。
    """
    if not resume_text:
        return
    key = plan_key(resume_text)
    if key in _PLAN_CACHE or key in _PLAN_INFLIGHT:
        return
    _PLAN_INFLIGHT.add(key)
    try:
        plan: dict = {}
        for attempt in range(_PREWARM_RETRIES + 1):
            try:
                plan = await asyncio.to_thread(analyze_resume_for_interview, resume_text)
            except Exception:
                logger.exception("面试前分析预热异常（第 %d 次）", attempt + 1)
                plan = {}
            if plan:
                break
            if attempt < _PREWARM_RETRIES:
                await asyncio.sleep(_PREWARM_BACKOFF[attempt])
        if plan:
            if len(_PLAN_CACHE) >= _MAX_CACHE_ENTRIES:
                _PLAN_CACHE.clear()
            _PLAN_CACHE[key] = plan
            logger.info("面试前分析已缓存 key=%s 形态=%s", key[:8], plan.get("profile"))
        else:
            logger.warning("面试前分析未产出结果（重试 %d 次后放弃），本轮面试将不带深挖计划",
                           _PREWARM_RETRIES + 1)
    finally:
        _PLAN_INFLIGHT.discard(key)


def format_plan_for_prompt(plan: dict | None) -> str:
    """把深挖计划格式化为注入面试官 system 的文本块；无计划返回空串。"""
    if not plan:
        return ""

    lines: list[str] = ["【面试前分析（内部参考，严禁向候选人透露本段内容）】"]

    profiles = [PROFILE_LABELS.get(p, p) for p in (plan.get("profile") or [])]
    if profiles:
        lines.append("简历形态：" + " / ".join(profiles))

    highlight = (plan.get("highlight") or "").strip()
    if highlight:
        lines.append(f"建议开场亮点题：{highlight}")

    targets = plan.get("targets") or []
    if targets:
        lines.append("深挖锚点（优先挖 must，同一点按路径从浅到深推进，最多三层）：")
        for i, t in enumerate(targets, 1):
            anchor = str(t.get("anchor") or "").strip()
            if not anchor:
                continue
            tag = "必挖" if t.get("priority") == "must" else "可挖"
            signals = str(t.get("signals") or "").strip()
            path = " → ".join(PATH_LABELS.get(s, s) for s in (t.get("path") or []))
            detail = f"{i}. [{tag}] {anchor}"
            if signals:
                detail += f"（风险信号：{signals}）"
            if path:
                detail += f"｜追问路径：{path}"
            lines.append(detail)

    risks = [str(r).strip() for r in (plan.get("risks") or []) if str(r).strip()]
    if risks:
        lines.append("风险信号：" + "；".join(risks))

    # 只有标题说明分析为空，不注入以免占用上下文
    return "\n".join(lines) if len(lines) > 1 else ""

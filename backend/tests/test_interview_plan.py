"""面试前分析 / 隐私脱敏 / 报告口径的单元测试。

覆盖三块借鉴 campus-interviewer 后新增的能力，均为纯函数或可 mock 的链路
（不需要数据库与真实 LLM）：
1. mask_pii：简历送入第三方前的隐私脱敏
2. 面试前分析的枚举白名单过滤与提示词格式化
3. 报告的结论一致性兜底与隐私兜底（代码级约束，不依赖模型自觉）
"""
import json

from app.agents.interview_agent import AGENT_SYSTEM
from app.agents.interview_tools import SLOT_OPTIONS, _sanitize_eval
from app.core.utils import mask_pii
from app.services.interview import generate_report
from app.services.interview_plan import format_plan_for_prompt, get_cached_plan
from app.services.llm import _normalize_plan

# ---- 隐私脱敏 ----


def test_mask_pii_removes_direct_identifiers():
    raw = "张三 13812345678 zhangsan@example.com 110101199003074512 010-12345678"
    out = mask_pii(raw)
    assert "13812345678" not in out
    assert "zhangsan@example.com" not in out
    assert "110101199003074512" not in out
    assert "010-12345678" not in out
    assert "[手机号已脱敏]" in out
    assert "[邮箱已脱敏]" in out


def test_mask_pii_is_idempotent():
    raw = "联系方式 13812345678，邮箱 a@b.com"
    once = mask_pii(raw)
    assert mask_pii(once) == once


def test_mask_pii_keeps_ordinary_numbers():
    """普通数字（年份、百分比、成绩）不能被误伤——简历里这类数字是追问依据。"""
    raw = "2026 年，性能提升 30%，专业排名前 10%，绩点 3.8"
    assert mask_pii(raw) == raw


def test_mask_pii_empty_text():
    assert mask_pii("") == ""


# ---- 面试前分析：规范化与格式化 ----


def test_normalize_plan_filters_unknown_enums_and_bad_items():
    plan = _normalize_plan({
        "profile": ["no_internship", "不存在的形态", "cross_major"],
        "highlight": "先问校园服务平台的并发抢单",
        "targets": [
            {
                "anchor": "校园综合服务平台",
                "signals": "数字口径不清",
                "priority": "MUST",
                "path": ["clarify", "乱写的动作", "dig"],
            },
            {"anchor": "", "priority": "may"},
            "not-a-dict",
        ],
        "risks": ["术语堆砌", ""],
    })
    assert plan["profile"] == ["no_internship", "cross_major"]
    assert len(plan["targets"]) == 1
    target = plan["targets"][0]
    assert target["anchor"] == "校园综合服务平台"
    assert target["priority"] == "must"
    assert target["path"] == ["clarify", "dig"]
    assert plan["risks"] == ["术语堆砌"]


def test_normalize_plan_caps_targets_at_six():
    plan = _normalize_plan({
        "targets": [{"anchor": f"锚点{i}", "priority": "may"} for i in range(10)],
    })
    assert len(plan["targets"]) == 6


def test_format_plan_for_prompt_empty_returns_blank():
    assert format_plan_for_prompt(None) == ""
    assert format_plan_for_prompt({}) == ""
    assert format_plan_for_prompt({"profile": [], "targets": [], "risks": []}) == ""


def test_format_plan_for_prompt_renders_must_and_path():
    text = format_plan_for_prompt({
        "profile": ["no_internship"],
        "highlight": "先问并发抢单",
        "targets": [{
            "anchor": "快递代拿抢单",
            "signals": "并发正确性未说明",
            "priority": "must",
            "path": ["clarify", "dig"],
        }],
        "risks": ["术语堆砌"],
    })
    assert "无实习型" in text          # 枚举翻成中文
    assert "必挖" in text              # 优先级标签
    assert "追问路径：澄清模糊表述 → 逼近机制与边界" in text
    assert "术语堆砌" in text
    assert "严禁向候选人透露" in text   # 内部参考声明


def test_get_cached_plan_miss_does_not_call_llm():
    """只读缓存：未命中必须返回 None，绝不能触发 LLM（构建 system 的路径不能阻塞）。"""
    assert get_cached_plan("一份从未分析过的简历文本") is None
    assert get_cached_plan("") is None


# ---- 面试官约束：防回退断言 ----


def test_agent_system_keeps_guardrails():
    """提示词回归测试：这些约束是本次借鉴 skill 的核心产出，不允许被后续改动删掉。"""
    for keyword in (
        "事实槽", "机制槽", "数字槽", "迁移槽", "反思槽",   # 九类槽位
        "三层追问", "澄清", "展开", "深挖",                 # 追问树
        "反套路",                                          # 防背稿
        "合规红线", "婚育状况", "院校出身", "家庭背景",      # 合规禁问领域
        "不臆造",                                          # 事实边界
        "{plan_block}",                                    # 深挖计划注入位
    ):
        assert keyword in AGENT_SYSTEM, f"AGENT_SYSTEM 缺少约束：{keyword}"


def test_sanitize_eval_validates_slot():
    bad = _sanitize_eval({"slot": "不存在的槽位", "follow_up": "不存在的信号"})
    assert bad["slot"] == "fact"
    assert bad["follow_up"] == "move_on"

    good = _sanitize_eval({"slot": "number", "follow_up": "clarify_role"})
    assert good["slot"] == "number"
    assert good["slot"] in SLOT_OPTIONS


# ---- 报告：代码级一致性兜底与隐私兜底 ----


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    """假 LLM：直接返回预设 JSON 文本，用于验证报告后处理逻辑。"""

    def __init__(self, payload: str):
        self._payload = payload

    async def ainvoke(self, messages):  # noqa: ARG002
        return _FakeMessage(self._payload)


def _payload(**overrides) -> str:
    base = {
        "overall_score": 80,
        "conclusion": "pass",
        "hire_signal": "hire",
        "summary": "整体尚可",
        "red_flags": [],
        "dimensions": [],
        "per_question": [],
        "patterns": {},
        "top_changes": [],
    }
    base.update(overrides)
    return json.dumps(base, ensure_ascii=False)


async def test_report_downgrades_conclusion_when_red_flag_triggered(monkeypatch):
    """红线触发而模型仍给 pass 时，由代码降级——不把硬规则交给模型自觉。"""
    monkeypatch.setattr(
        "app.services.interview._build_llm",
        lambda: _FakeLLM(_payload(conclusion="pass", red_flags=["背稿式回答：通篇模板化"])),
    )
    report = await generate_report("简历", "AI应用开发", [{"role": "user", "content": "我的回答"}])
    assert report["conclusion"] == "pending"
    assert report["red_flags"]


async def test_report_keeps_valid_conclusion(monkeypatch):
    monkeypatch.setattr(
        "app.services.interview._build_llm",
        lambda: _FakeLLM(_payload(conclusion="fail", hire_signal="no_hire")),
    )
    report = await generate_report("简历", "AI应用开发", [{"role": "user", "content": "我的回答"}])
    assert report["conclusion"] == "fail"


async def test_report_clears_invalid_conclusion(monkeypatch):
    monkeypatch.setattr(
        "app.services.interview._build_llm",
        lambda: _FakeLLM(_payload(conclusion="综合得分87分")),
    )
    report = await generate_report("简历", "AI应用开发", [{"role": "user", "content": "我的回答"}])
    assert report["conclusion"] == ""


async def test_report_masks_pii_in_quotes(monkeypatch):
    """模型可能把简历里的联系方式写进报告，落库前必须再脱敏一次。"""
    monkeypatch.setattr(
        "app.services.interview._build_llm",
        lambda: _FakeLLM(_payload(
            per_question=[{
                "index": 1,
                "question": "自我介绍",
                "scores": {},
                "strongest": "他说手机号是 13812345678，邮箱 a@b.com",
                "missed": "",
            }],
        )),
    )
    report = await generate_report("简历", "AI应用开发", [{"role": "user", "content": "我的回答"}])
    dumped = json.dumps(report, ensure_ascii=False)
    assert "13812345678" not in dumped
    assert "a@b.com" not in dumped
    assert "[手机号已脱敏]" in dumped


async def test_report_returns_empty_on_invalid_json(monkeypatch):
    monkeypatch.setattr(
        "app.services.interview._build_llm",
        lambda: _FakeLLM("这不是 JSON"),
    )
    report = await generate_report("简历", "AI应用开发", [{"role": "user", "content": "我的回答"}])
    assert report == {}

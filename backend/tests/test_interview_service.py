"""interview 服务单测：消息构建与历史裁剪（不调用真实 LLM）。"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.interview import MAX_HISTORY_ROUNDS, build_interview_messages


def _history(n_rounds: int) -> list[dict]:
    out = []
    for i in range(n_rounds):
        out.append({"role": "assistant", "content": f"问题{i}"})
        out.append({"role": "user", "content": f"回答{i}"})
    return out


def test_build_messages_contains_system_resume():
    msgs = build_interview_messages("我的简历内容", "后端开发", _history(1))
    assert isinstance(msgs[0], SystemMessage)
    assert "后端开发" in msgs[0].content
    assert "我的简历内容" in msgs[0].content


def test_build_messages_trims_history():
    msgs = build_interview_messages("简历", "测试岗", _history(20))
    # system 1 条 + 最近 10 轮 20 条
    assert len(msgs) == 1 + MAX_HISTORY_ROUNDS * 2
    assert msgs[-1].content == "回答19"


def test_build_messages_role_mapping():
    msgs = build_interview_messages("简历", "测试岗", [{"role": "user", "content": "你好"}])
    assert isinstance(msgs[-1], HumanMessage)
    msgs = build_interview_messages("简历", "测试岗", [{"role": "assistant", "content": "你好"}])
    assert isinstance(msgs[-1], AIMessage)

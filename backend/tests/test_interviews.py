"""模拟面试 API 集成测试：mock LLM 服务，验证流程/权限/状态机。"""
import json

import pytest


async def _fake_stream(resume_text, job_position, history):
    assert "后端" in job_position
    for chunk in ["请先", "自我介绍。"]:
        yield chunk


async def _fake_report(*args, **kwargs):
    return {
        "overall_score": 85,
        "dimensions": [{"name": "表达逻辑", "score": 80, "comment": "结构清晰"}],
        "strengths": ["项目经验扎实"],
        "weaknesses": ["量化不足"],
        "suggestions": ["补充数据"],
    }


@pytest.fixture
def mock_llm(monkeypatch):
    monkeypatch.setattr("app.api.interviews.stream_question", _fake_stream)
    monkeypatch.setattr("app.api.interviews.generate_report", _fake_report)


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        event, data = "message", ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: "):
                data = line[6:]
        if data:
            events.append((event, json.loads(data)))
    return events


async def test_create_and_chat_flow(auth_client, mock_llm):
    # 创建 → start + 首题 delta... + done
    resp = await auth_client.post("/api/v1/interviews", json={"job_position": "后端开发"})
    assert resp.status_code == 201
    events = _parse_sse(resp.text)
    kinds = [e for e, _ in events]
    assert kinds[0] == "start"
    assert kinds[1:-1] == ["delta", "delta"]
    assert kinds[-1] == "done"
    interview_id = events[0][1]["interview_id"]
    question = "".join(d["text"] for e, d in events if e == "delta")
    assert question == "请先自我介绍。"

    # 详情：首题已落库
    resp = await auth_client.get(f"/api/v1/interviews/{interview_id}")
    assert resp.status_code == 200
    assert resp.json()["messages"][0]["role"] == "assistant"
    assert resp.json()["messages"][0]["content"] == "请先自我介绍。"

    # 对话 → SSE 追问 + 用户消息落库
    resp = await auth_client.post(
        f"/api/v1/interviews/{interview_id}/chat", json={"content": "我叫张三，做过XX项目"}
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [e for e, _ in events][-1] == "done"

    resp = await auth_client.get(f"/api/v1/interviews/{interview_id}")
    msgs = resp.json()["messages"]
    assert [m["role"] for m in msgs] == ["assistant", "user", "assistant"]

    # 结束 → 报告
    resp = await auth_client.post(f"/api/v1/interviews/{interview_id}/finish")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
    assert resp.json()["report"]["overall_score"] == 85

    # 结束后不能再对话
    resp = await auth_client.post(
        f"/api/v1/interviews/{interview_id}/chat", json={"content": "再问一个"}
    )
    assert resp.status_code == 400


async def test_forbidden_access(auth_client, client, mock_llm):
    resp = await auth_client.post("/api/v1/interviews", json={"job_position": "后端开发"})
    interview_id = _parse_sse(resp.text)[0][1]["interview_id"]

    # 另一个用户访问 → 403
    resp = await client.post("/api/v1/auth/register", json={
        "username": "other", "email": "other@test.com", "password": "pass1234"
    })
    client.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
    resp = await client.get(f"/api/v1/interviews/{interview_id}")
    assert resp.status_code == 403


async def test_create_with_not_own_resume(auth_client, mock_llm):
    from app.models.resume import ParseStatus, Resume
    from app.models.user import User
    from tests.conftest import TestingSessionLocal

    # 直接在测试库造一份属于别人的简历
    async with TestingSessionLocal() as db:
        u = User(username="owner", email="owner@test.com", hashed_password="x")
        db.add(u)
        await db.commit()
        r = Resume(
            user_id=u.id, file_name="a.pdf", file_path="/x",
            raw_text="别人", parse_status=ParseStatus.completed,
        )
        db.add(r)
        await db.commit()
        resume_id = r.id

    resp = await auth_client.post(
        "/api/v1/interviews", json={"resume_id": resume_id, "job_position": "后端开发"}
    )
    assert resp.status_code == 404


async def test_list(auth_client, mock_llm):
    await auth_client.post("/api/v1/interviews", json={"job_position": "后端开发"})
    resp = await auth_client.get("/api/v1/interviews")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["message_count"] == 1

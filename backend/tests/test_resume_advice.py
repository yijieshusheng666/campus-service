"""AI 优化建议 API 测试：mock LLM，验证生成落库/覆盖/权限/状态校验。"""
import pytest

from app.models.resume import ParseStatus, Resume
from app.models.user import User
from tests.conftest import TestingSessionLocal

_FAKE_ADVICE = {
    "overall_score": 72,
    "summary": "整体结构清晰，但量化不足",
    "items": [
        {
            "module": "项目经历",
            "priority": "high",
            "issue": "医疗项目未写量化结果",
            "advice": "改为：QPS 从 X 提升至 Y",
        },
        {
            "module": "技能",
            "priority": "low",
            "issue": "技能罗列未分优先级",
            "advice": "按熟练程度分组呈现",
        },
    ],
}


@pytest.fixture
def mock_advice(monkeypatch):
    monkeypatch.setattr("app.api.resumes.advise_resume", lambda *a, **kw: dict(_FAKE_ADVICE))


async def _create_resume(user_id: int, status: ParseStatus = ParseStatus.completed) -> int:
    async with TestingSessionLocal() as db:
        r = Resume(
            user_id=user_id, file_name="a.pdf", file_path="/x",
            raw_text="测试简历内容", parse_status=status,
        )
        db.add(r)
        await db.commit()
        await db.refresh(r)
        return r.id


async def _auth_user_id() -> int:
    async with TestingSessionLocal() as db:
        u = (
            await db.execute(
                User.__table__.select().where(User.__table__.c.username == "tester")
            )
        ).first()
        return u.id


async def test_generate_and_overwrite(auth_client, mock_advice, monkeypatch):
    resume_id = await _create_resume(await _auth_user_id())

    # 首次生成：落库并返回
    resp = await auth_client.post(f"/api/v1/resumes/{resume_id}/advice", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["suggestions"]["overall_score"] == 72
    assert len(data["suggestions"]["items"]) == 2
    assert data["suggestions_at"] is not None

    # 再次生成：覆盖为最新一轮
    monkeypatch.setattr(
        "app.api.resumes.advise_resume",
        lambda *a, **kw: {
            "overall_score": 80,
            "summary": "第二轮",
            "items": [{"module": "教育", "priority": "medium", "issue": "i", "advice": "a"}],
        },
    )
    resp = await auth_client.post(f"/api/v1/resumes/{resume_id}/advice", json={})
    assert resp.status_code == 200
    assert resp.json()["suggestions"]["summary"] == "第二轮"
    assert len(resp.json()["suggestions"]["items"]) == 1


async def test_advice_not_completed_rejected(auth_client, mock_advice):
    resume_id = await _create_resume(await _auth_user_id(), ParseStatus.failed)
    resp = await auth_client.post(f"/api/v1/resumes/{resume_id}/advice", json={})
    assert resp.status_code == 400


async def test_advice_forbidden(auth_client, client, mock_advice):
    owner_id = await _auth_user_id()
    resume_id = await _create_resume(owner_id)

    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "other", "email": "other@test.com", "password": "pass1234"},
    )
    client.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
    resp = await client.post(f"/api/v1/resumes/{resume_id}/advice", json={})
    assert resp.status_code == 403


async def test_advice_llm_failure(auth_client, monkeypatch):
    resume_id = await _create_resume(await _auth_user_id())

    monkeypatch.setattr("app.api.resumes.advise_resume", lambda *a, **kw: {})
    resp = await auth_client.post(f"/api/v1/resumes/{resume_id}/advice", json={})
    assert resp.status_code == 502

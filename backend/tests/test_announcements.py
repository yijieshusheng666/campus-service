"""平台公告：浏览权限、上下架规则、管理端 CRUD。"""
import pytest
from sqlalchemy import select

from app.models.user import User
from tests.conftest import TestingSessionLocal


@pytest.fixture
async def admin_client(auth_client):
    async with TestingSessionLocal() as db:
        user = (await db.execute(select(User).where(User.username == "tester"))).scalar_one()
        user.is_admin = True
        await db.commit()
    yield auth_client


async def _create(admin_client, title="期中考试安排", content="第 10 周期中考试，具体考场见教务系统。"):
    resp = await admin_client.post(
        "/api/v1/announcements", json={"title": title, "content": content}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_admin_can_create_announcement(admin_client):
    data = await _create(admin_client)
    assert data["title"] == "期中考试安排"
    assert data["is_online"] is True
    assert data["publisher"]["username"] == "tester"


async def test_non_admin_cannot_create(auth_client):
    resp = await auth_client.post(
        "/api/v1/announcements", json={"title": "x", "content": "y"}
    )
    assert resp.status_code == 403


async def test_list_requires_login(client):
    resp = await client.get("/api/v1/announcements")
    assert resp.status_code == 401


async def test_list_shows_only_online_and_pinned_first(admin_client, auth_client):
    await _create(admin_client, title="普通公告A")
    pinned = await _create(admin_client, title="置顶公告B")
    # 下架 A
    a_id = (await auth_client.get("/api/v1/announcements")).json()["items"][-1]["id"]
    resp = await admin_client.put(f"/api/v1/announcements/{a_id}", json={"is_online": False})
    assert resp.status_code == 200

    resp = await auth_client.get("/api/v1/announcements")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == pinned["id"]
    assert body["items"][0]["is_pinned"] is False  # 未置顶，只是唯一在线

    # 置顶后应排在最前
    await _create(admin_client, title="普通公告C")
    await admin_client.put(f"/api/v1/announcements/{pinned['id']}", json={"is_pinned": True})
    body = (await auth_client.get("/api/v1/announcements")).json()
    assert body["items"][0]["id"] == pinned["id"]
    assert body["items"][0]["is_pinned"] is True


async def test_detail_offline_returns_404(admin_client, auth_client):
    data = await _create(admin_client)
    await admin_client.put(f"/api/v1/announcements/{data['id']}", json={"is_online": False})
    resp = await auth_client.get(f"/api/v1/announcements/{data['id']}")
    assert resp.status_code == 404


async def test_admin_can_delete(admin_client, auth_client):
    data = await _create(admin_client)
    resp = await admin_client.delete(f"/api/v1/announcements/{data['id']}")
    assert resp.status_code == 204
    resp = await auth_client.get(f"/api/v1/announcements/{data['id']}")
    assert resp.status_code == 404


async def test_manage_lists_offline_for_admin_only(admin_client, client):
    """管理端 /manage 含已下架公告；普通用户访问被拒。"""
    data = await _create(admin_client)
    await admin_client.put(f"/api/v1/announcements/{data['id']}", json={"is_online": False})

    resp = await admin_client.get("/api/v1/announcements/manage")
    assert resp.status_code == 200
    assert any(item["id"] == data["id"] and item["is_online"] is False for item in resp.json())
    # /manage 必须返回正文（编辑表单直接用）
    assert resp.json()[0]["content"]

    # 另注册一个普通用户（注意 admin_client/auth_client 共享同一底层 client，
    # 且 tester 已被提升为管理员，必须用全新账号验证 403）
    reg = await client.post(
        "/api/v1/auth/register",
        json={"username": "normal1", "email": "n1@test.com", "password": "pass1234"},
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    resp = await client.get(
        "/api/v1/announcements/manage", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403

"""快递代拿 API 集成测试：状态机全路径 + 行锁并发接单 + 权限。"""
import asyncio

import pytest


async def _register(client, username: str) -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@test.com", "password": "pass1234"},
    )
    return f"Bearer {resp.json()['access_token']}"


async def _publish(client: object, token: str) -> int:
    resp = await client.post(
        "/api/v1/errands",
        json={
            "pickup_location": "菜鸟驿站3号店",
            "package_info": "顺丰 SF1234567890",
            "dropoff_location": "梧桐苑5栋302",
            "reward": "3.50",
            "remark": "放门口即可",
        },
        headers={"Authorization": token},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_full_lifecycle(auth_client, client):
    """pending → accepted → delivered → completed 全链路。"""
    pub_token = auth_client.headers["Authorization"]
    errand_id = await _publish(auth_client, pub_token)

    runner_token = await _register(client, "runner1")
    # 接单
    resp = await client.put(f"/api/v1/errands/{errand_id}/accept", headers={"Authorization": runner_token})
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert resp.json()["runner"]["username"] == "runner1"

    # 送达（发布者不能送达）
    resp = await client.put(
        f"/api/v1/errands/{errand_id}/status", json={"status": "delivered"},
        headers={"Authorization": pub_token},
    )
    assert resp.status_code == 403
    resp = await client.put(
        f"/api/v1/errands/{errand_id}/status", json={"status": "delivered"},
        headers={"Authorization": runner_token},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "delivered"

    # 结算（跑腿员不能结算）
    resp = await client.put(
        f"/api/v1/errands/{errand_id}/status", json={"status": "completed"},
        headers={"Authorization": runner_token},
    )
    assert resp.status_code == 403
    resp = await client.put(
        f"/api/v1/errands/{errand_id}/status", json={"status": "completed"},
        headers={"Authorization": pub_token},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


async def test_cancel(auth_client):
    errand_id = await _publish(auth_client, auth_client.headers["Authorization"])
    resp = await auth_client.put(f"/api/v1/errands/{errand_id}/status", json={"status": "cancelled"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_cannot_accept_own(auth_client):
    errand_id = await _publish(auth_client, auth_client.headers["Authorization"])
    resp = await auth_client.put(f"/api/v1/errands/{errand_id}/accept")
    assert resp.status_code == 400


async def test_concurrent_accept(auth_client, client):
    """行锁并发接单：两个跑腿员同时抢，只有一个成功。"""
    import tests.conftest as c
    from httpx import ASGITransport, AsyncClient
    from app.api.errands import get_db

    errand_id = await _publish(auth_client, auth_client.headers["Authorization"])

    # 两个独立客户端（各自携带依赖注入的 session，才能模拟并发事务）
    async def _try_accept(username: str) -> int:
        token = await _register(client, username)
        async with AsyncClient(transport=ASGITransport(app=c.app), base_url="http://test") as ac:
            resp = await ac.put(
                f"/api/v1/errands/{errand_id}/accept", headers={"Authorization": token}
            )
            return resp.status_code

    codes = await asyncio.gather(_try_accept("runner_a"), _try_accept("runner_b"))
    assert sorted(codes) == [200, 400], f"应恰好一个成功一个被拒，实际: {codes}"


async def test_hall_excludes_own(auth_client, client):
    await _publish(auth_client, auth_client.headers["Authorization"])
    # 大厅：发布者自己看不到
    resp = await auth_client.get("/api/v1/errands")
    assert resp.status_code == 200
    assert resp.json() == []

    # 其他人能看到
    token = await _register(client, "watcher")
    resp = await client.get("/api/v1/errands", headers={"Authorization": token})
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # published 视图：发布者能看到自己发布的
    resp = await auth_client.get("/api/v1/errands?role=published")
    assert len(resp.json()) == 1

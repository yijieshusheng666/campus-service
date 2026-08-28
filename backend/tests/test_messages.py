"""私信测试：WebSocket 协议（替身直调端点，同事件循环）+ REST 会话/历史/已读。"""
from fastapi import WebSocketDisconnect

from app.api.ws import manager, ws_endpoint
from app.core.security import create_access_token, hash_password
from app.models.message import Message
from app.models.user import User
from tests.conftest import TestingSessionLocal


class FakeWebSocket:
    """测试用 WebSocket 替身：脚本化输入、记录输出。"""

    def __init__(self, token: str | None = None, script: list | None = None):
        self.query_params = {"token": token} if token else {}
        self.script = list(script or [])
        self.sent: list[dict] = []
        self.close_code: int | None = None

    async def accept(self):
        pass

    async def close(self, code: int | None = None):
        self.close_code = code

    async def receive_json(self):
        if not self.script:
            raise WebSocketDisconnect(code=1000)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def send_json(self, data: dict):
        self.sent.append(data)


async def _make_user(username: str) -> int:
    async with TestingSessionLocal() as db:
        u = User(
            username=username,
            email=f"{username}@test.com",
            hashed_password=hash_password("pass1234"),
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u.id


async def _run_ws(token: str, script: list) -> FakeWebSocket:
    ws = FakeWebSocket(token=token, script=script)
    async with TestingSessionLocal() as db:
        await ws_endpoint(ws, db)
    return ws


# ---- WebSocket ----
async def test_ws_invalid_token_closed():
    """无效 token：连接被拒绝并关闭（code 4401）。"""
    ws = await _run_ws("not-a-jwt", [])
    assert ws.close_code == 4401


async def test_ws_chat_ack_push_and_persist(client):
    """发消息：发送方收 ack、接收方收实时推送、消息落库可 REST 拉取。"""
    alice_id = await _make_user("alice")
    bob_id = await _make_user("bob")

    bob_ws = FakeWebSocket()
    await manager.connect(bob_id, bob_ws)
    try:
        alice_ws = await _run_ws(
            create_access_token(str(alice_id)),
            [{"type": "chat", "receiver_id": bob_id, "content": "你好"}],
        )
    finally:
        manager.disconnect(bob_id, bob_ws)

    ack = [m for m in alice_ws.sent if m["type"] == "chat_ack"]
    assert ack and ack[0]["content"] == "你好" and ack[0]["receiver_id"] == bob_id

    push = [m for m in bob_ws.sent if m["type"] == "new_message"]
    assert push and push[0]["sender_id"] == alice_id and push[0]["content"] == "你好"

    # 落库校验：alice 视角拉历史
    resp = await client.get(
        f"/api/v1/messages/{bob_id}",
        headers={"Authorization": f"Bearer {create_access_token(str(alice_id))}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1 and data[0]["content"] == "你好"


async def test_ws_offline_receiver_no_push_but_persisted(client):
    """接收方离线：无推送，消息照常落库，上线后 REST 补拉。"""
    alice_id = await _make_user("alice")
    bob_id = await _make_user("bob")

    alice_ws = await _run_ws(
        create_access_token(str(alice_id)),
        [{"type": "chat", "receiver_id": bob_id, "content": "离线消息"}],
    )
    assert any(m["type"] == "chat_ack" for m in alice_ws.sent)

    resp = await client.get(
        f"/api/v1/messages/{alice_id}",
        headers={"Authorization": f"Bearer {create_access_token(str(bob_id))}"},
    )
    assert [m["content"] for m in resp.json()] == ["离线消息"]


async def test_ws_protocol_errors():
    """协议防御：未知类型 / 给自己发 / 接收者不存在。"""
    uid = await _make_user("solo")
    other_id = await _make_user("ghost_target")

    ws = await _run_ws(
        create_access_token(str(uid)),
        [
            {"type": "unknown_type"},
            {"type": "chat", "receiver_id": uid, "content": "自言自语"},
            {"type": "chat", "receiver_id": 99999, "content": "发给不存在的人"},
        ],
    )
    errors = [m for m in ws.sent if m["type"] == "error"]
    assert len(errors) == 3, f"应返回 3 个 error，实际: {ws.sent}"

    # 存在的接收者但消息非法（空内容）
    ws2 = await _run_ws(
        create_access_token(str(uid)),
        [{"type": "chat", "receiver_id": other_id, "content": "   "}],
    )
    assert [m["type"] for m in ws2.sent] == ["error"]


async def test_ws_ping_pong():
    uid = await _make_user("pinger")
    ws = await _run_ws(
        create_access_token(str(uid)),
        [{"type": "ping"}, {"type": "ping"}],
    )
    assert [m["type"] for m in ws.sent] == ["pong", "pong"]


# ---- REST ----
async def test_conversations_unread_and_mark_read(client):
    """会话聚合：最近消息 + 未读数；标记已读后清零。"""
    alice_id = await _make_user("alice")
    bob_id = await _make_user("bob")
    carol_id = await _make_user("carol")

    async with TestingSessionLocal() as db:
        db.add_all(
            [
                Message(sender_id=bob_id, receiver_id=alice_id, content="m1"),
                Message(sender_id=alice_id, receiver_id=bob_id, content="m2"),
                Message(sender_id=carol_id, receiver_id=alice_id, content="hi"),
                Message(sender_id=bob_id, receiver_id=alice_id, content="m3"),
            ]
        )
        await db.commit()

    headers = {"Authorization": f"Bearer {create_access_token(str(alice_id))}"}
    resp = await client.get("/api/v1/messages/conversations", headers=headers)
    assert resp.status_code == 200
    convs = {c["username"]: c for c in resp.json()}
    assert len(convs) == 2
    assert convs["bob"]["last_message"] == "m3"
    assert convs["bob"]["unread"] == 2
    assert convs["carol"]["last_message"] == "hi"
    assert convs["carol"]["unread"] == 1
    # 按最后消息时间倒序
    assert resp.json()[0]["username"] == "bob"

    # 标记 bob 会话已读
    resp = await client.put(f"/api/v1/messages/{bob_id}/read", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["read"] == 2

    resp = await client.get("/api/v1/messages/conversations", headers=headers)
    convs = {c["username"]: c for c in resp.json()}
    assert convs["bob"]["unread"] == 0
    assert convs["carol"]["unread"] == 1


async def test_history_cursor_pagination(client):
    """历史消息游标分页：倒序取页、正序返回、before_id 翻页。"""
    alice_id = await _make_user("alice")
    bob_id = await _make_user("bob")

    async with TestingSessionLocal() as db:
        for i in range(1, 6):
            sender, receiver = (bob_id, alice_id) if i % 2 else (alice_id, bob_id)
            db.add(Message(sender_id=sender, receiver_id=receiver, content=f"m{i}"))
        await db.commit()

    headers = {"Authorization": f"Bearer {create_access_token(str(alice_id))}"}
    resp = await client.get(f"/api/v1/messages/{bob_id}?limit=3", headers=headers)
    page1 = resp.json()
    assert [m["content"] for m in page1] == ["m3", "m4", "m5"]

    resp = await client.get(
        f"/api/v1/messages/{bob_id}?before_id={page1[0]['id']}&limit=3", headers=headers
    )
    page2 = resp.json()
    assert [m["content"] for m in page2] == ["m1", "m2"]


async def test_history_user_not_found(client, auth_client):
    resp = await auth_client.get("/api/v1/messages/99999")
    assert resp.status_code == 404

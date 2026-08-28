"""WebSocket 私信：连接管理 + 实时收发。

浏览器 WebSocket 无法自定义 header，鉴权 token 走 query 参数。
消息可靠性策略：落库优先，推送失败不影响持久化，接收方上线后 REST 拉历史补齐。
"""
import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.database import get_db
from app.models.message import Message
from app.models.user import User

router = APIRouter()

# 鉴权失败关闭码（4xxx 为应用自定义区间）
WS_CLOSE_UNAUTHORIZED = 4401


class ConnectionManager:
    """user_id -> 该账号所有在线 WebSocket 连接。

    支持同一账号多设备同时在线：同一用户开 N 个标签页就有 N 条连接，
    推送时逐条发送，单条失败只摘除该连接，不影响其他设备。
    """

    def __init__(self) -> None:
        self._connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(user_id, []).append(ws)

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        conns = self._connections.get(user_id)
        if conns and ws in conns:
            conns.remove(ws)
            if not conns:
                self._connections.pop(user_id, None)

    async def send_json_to_user(self, user_id: int, payload: dict) -> None:
        """推送给某用户全部在线连接；失败连接就地摘除（消息已落库不丢）。"""
        for ws in list(self._connections.get(user_id, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(user_id, ws)


manager = ConnectionManager()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket, db: AsyncSession = Depends(get_db)):
    # ---- 鉴权：query token -> user_id ----
    # 先 accept 再 close(4401)：握手期直接拒绝只会得到 HTTP 403，浏览器侧拿不到自定义关闭码
    token = ws.query_params.get("token", "")
    try:
        payload = decode_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        await ws.accept()
        await ws.close(code=WS_CLOSE_UNAUTHORIZED)
        return

    await manager.connect(user_id, ws)
    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                await ws.send_json({"type": "pong"})
                continue

            if msg_type != "chat":
                await ws.send_json({"type": "error", "detail": "未知消息类型"})
                continue

            receiver_id = data.get("receiver_id")
            content = str(data.get("content") or "").strip()
            if not isinstance(receiver_id, int) or not content:
                await ws.send_json({"type": "error", "detail": "参数不合法"})
                continue
            if receiver_id == user_id:
                await ws.send_json({"type": "error", "detail": "不能给自己发私信"})
                continue
            if len(content) > 2000:
                await ws.send_json({"type": "error", "detail": "消息过长（上限 2000 字）"})
                continue
            if await db.get(User, receiver_id) is None:
                await ws.send_json({"type": "error", "detail": "接收者不存在"})
                continue

            # ---- 落库优先 ----
            message = Message(sender_id=user_id, receiver_id=receiver_id, content=content)
            db.add(message)
            await db.commit()
            await db.refresh(message)

            # 发送方所有连接 ack（多端登录时每台设备都收到确认）
            await manager.send_json_to_user(
                user_id,
                {
                    "type": "chat_ack",
                    "message_id": message.id,
                    "receiver_id": receiver_id,
                    "content": content,
                    "created_at": message.created_at.isoformat(),
                },
            )
            # 接收方在线连接实时推送；离线则静默（上线后 REST 拉历史）
            await manager.send_json_to_user(
                receiver_id,
                {
                    "type": "new_message",
                    "id": message.id,
                    "sender_id": user_id,
                    "content": content,
                    "created_at": message.created_at.isoformat(),
                },
            )
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id, ws)

"""WebSocket 私信：连接管理 + 实时收发。

浏览器 WebSocket 无法自定义 header，鉴权 token 走 query 参数。
消息可靠性策略：落库优先，推送失败不影响持久化，接收方上线后 REST 拉历史补齐。

多进程推送（分布式模式）：
- 单机模式（REDIS_URL 空）：推送只发到本进程内存里的连接，workers 只能开 1。
- 分布式模式（REDIS_URL 已配）：推送统一走 Redis pub/sub，每个 worker 的监听协程
  把消息投递给本进程里的目标连接。这样用户无论连到哪个 worker 都能收到消息，
  uvicorn workers 可以多开。见 start_redis_bridge()。
"""
import asyncio
import contextlib
import json
import logging

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.redis_client import get_redis
from app.core.security import decode_token
from app.database import get_db
from app.models.goods import Goods
from app.models.message import Message
from app.models.user import User
from app.schemas.message import GoodsBriefOut

logger = logging.getLogger(__name__)

router = APIRouter()

# 鉴权失败关闭码（4xxx 为应用自定义区间）
WS_CLOSE_UNAUTHORIZED = 4401

# Redis pub/sub 频道：跨 worker 投递私信推送
WS_CHANNEL = "campus:ws"
_redis_listener: asyncio.Task | None = None


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
        """推送给本进程内某用户全部在线连接；失败连接就地摘除（消息已落库不丢）。"""
        for ws in list(self._connections.get(user_id, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(user_id, ws)


manager = ConnectionManager()


async def send_to_user(user_id: int, payload: dict) -> None:
    """推送入口：分布式模式走 Redis pub/sub（全集群可达），单机模式直发本进程。

    分布式模式下不直发本进程、统一等监听协程回投，否则「直发 + 回投」会重复投递。
    """
    redis = get_redis()
    if redis is None:
        await manager.send_json_to_user(user_id, payload)
        return
    await redis.publish(WS_CHANNEL, json.dumps({"user_id": user_id, "payload": payload}))


async def _redis_listen_loop() -> None:
    """订阅推送频道，把消息投递给本进程内的目标连接。"""
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(WS_CHANNEL)
    logger.info("WS Redis 推送桥已启动（频道 %s）", WS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                data = json.loads(message["data"])
                await manager.send_json_to_user(int(data["user_id"]), data["payload"])
            except Exception:
                logger.exception("WS 推送桥投递失败")
    finally:
        await pubsub.unsubscribe(WS_CHANNEL)
        await pubsub.aclose()


async def start_redis_bridge() -> None:
    """应用启动时调用：仅分布式模式启动监听协程。"""
    global _redis_listener
    if get_redis() is None or _redis_listener is not None:
        return
    _redis_listener = asyncio.create_task(_redis_listen_loop())


async def stop_redis_bridge() -> None:
    """应用关停时调用：取消监听协程。"""
    global _redis_listener
    if _redis_listener is not None:
        _redis_listener.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _redis_listener
        _redis_listener = None


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
            goods_id = data.get("goods_id")
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

            # ---- 商品卡片：可选附带一件商品 ----
            # 在服务端校验存在性而不是信任前端传的 id：伪造的 goods_id 会让
            # 接收方渲染出一张指向不存在商品的卡片（点击即 404）
            goods_brief = None
            if goods_id is not None:
                if not isinstance(goods_id, int):
                    await ws.send_json({"type": "error", "detail": "商品参数不合法"})
                    continue
                goods = (
                    await db.execute(
                        select(Goods)
                        .where(Goods.id == goods_id)
                        .options(selectinload(Goods.images))
                    )
                ).scalar_one_or_none()
                if goods is None:
                    await ws.send_json({"type": "error", "detail": "商品不存在或已删除"})
                    continue
                goods_brief = GoodsBriefOut.model_validate(goods).model_dump(mode="json")

            # ---- 落库优先 ----
            message = Message(
                sender_id=user_id,
                receiver_id=receiver_id,
                content=content,
                goods_id=goods_id,
            )
            db.add(message)
            await db.commit()
            await db.refresh(message)

            # 发送方所有连接 ack（多端登录时每台设备都收到确认）
            await send_to_user(
                user_id,
                {
                    "type": "chat_ack",
                    "message_id": message.id,
                    "receiver_id": receiver_id,
                    "content": content,
                    "goods_id": goods_id,
                    "goods": goods_brief,
                    "created_at": message.created_at.isoformat(),
                },
            )
            # 接收方在线连接实时推送；离线则静默（上线后 REST 拉历史）
            await send_to_user(
                receiver_id,
                {
                    "type": "new_message",
                    "id": message.id,
                    "sender_id": user_id,
                    "content": content,
                    "goods_id": goods_id,
                    "goods": goods_brief,
                    "created_at": message.created_at.isoformat(),
                },
            )
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id, ws)

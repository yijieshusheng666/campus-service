"""智能客服 API（v2 行动型 + v3 SSE 流式）：LLM 问答 + 商品发布任务状态机。"""
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.agents.support_agent import (
    agent_chat,
    agent_chat_stream,
    clear_history,
    get_history,
)
from app.models.user import User
from app.schemas.support import SupportChatIn, SupportChatOut

router = APIRouter(prefix="/support", tags=["智能客服"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def support_chat(
    payload: SupportChatIn,
    user: User = Depends(get_current_user),
):
    """客服对话（v3 SSE 流式 + v2 同步兼容）。

    默认启用 SSE 流式输出（stream=true），前端用 EventSource 接收。
    旧客户端可传 stream=false 获得一次性 JSON（与 v2 完全兼容）。
    支持多轮对话上下文记忆（per-user，30分钟过期）。
    """
    if not payload.question.strip() and not payload.image_urls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="问题或图片至少提供一个"
        )
    if len(payload.image_urls) > 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="单次最多上传6张图片"
        )

    if payload.stream:
        async def gen():
            async for event in agent_chat_stream(
                user.id,
                payload.question.strip(),
                image_urls=payload.image_urls or None,
            ):
                event_type = event.pop("type", "unknown")
                yield _sse(event_type, event)

        return StreamingResponse(
            gen(), media_type="text/event-stream"
        )

    # 同步降级（v2 兼容）
    result = await agent_chat(
        user.id,
        payload.question.strip(),
        image_urls=payload.image_urls or None,
    )
    return SupportChatOut(**result)


@router.get("/history", response_model=list[dict])
async def support_history(
    user: User = Depends(get_current_user),
):
    """获取当前用户的客服对话历史。"""
    return get_history(user.id)


@router.post("/clear", response_model=dict)
async def support_clear(
    user: User = Depends(get_current_user),
):
    """清空当前用户的客服对话历史与任务状态。"""
    clear_history(user.id)
    return {"status": "ok", "message": "对话历史已清空"}
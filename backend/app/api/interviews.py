"""AI 模拟面试 API：创建(SSE 首题) / 列表 / 详情 / 对话(SSE) / 结束生成报告。"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import AsyncSessionLocal, get_db
from app.models.interview import InterviewMessage, InterviewStatus, MockInterview
from app.models.resume import Resume
from app.models.user import User
from app.schemas.interview import InterviewChatIn, InterviewCreate, InterviewDetailOut, InterviewOut
from app.services.interview import generate_report, stream_question

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interviews", tags=["模拟面试"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _load_own_interview(db: AsyncSession, interview_id: int, user: User) -> MockInterview:
    itv = (
        await db.execute(
            select(MockInterview)
            .options(selectinload(MockInterview.messages))
            .where(MockInterview.id == interview_id)
        )
    ).scalar_one_or_none()
    if not itv:
        raise HTTPException(status_code=404, detail="面试会话不存在")
    if itv.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该面试会话")
    return itv


def _resume_to_text(resume: Resume | None) -> str:
    """把简历转为注入 LLM 的文本：优先用户编辑版，其次解析结果，最后原文。"""
    if not resume:
        return ""
    data = resume.edited_data or {}
    sections = data.get("sections") or resume.parsed_sections or []
    if sections:
        parts = [
            f"姓名：{data.get('name') or resume.parsed_name or ''}",
            f"求职意向：{data.get('job_title') or resume.parsed_job_title or ''}",
        ]
        for sec in sections:
            parts.append(f"\n## {sec.get('title', '')}")
            for it in sec.get("items", []):
                head = " / ".join(
                    x for x in (it.get("heading"), it.get("subheading"), it.get("date")) if x
                )
                parts.append(f"- {head}\n  {it.get('description', '')}" if head else f"- {it.get('description', '')}")
        return "\n".join(parts)
    return resume.raw_text or ""


def _to_out(itv: MockInterview) -> dict:
    msgs = itv.messages or []
    return {
        "id": itv.id,
        "resume_id": itv.resume_id,
        "job_position": itv.job_position,
        "status": itv.status,
        "created_at": itv.created_at,
        "updated_at": itv.updated_at,
        "message_count": len(msgs),
        "last_content": msgs[-1].content if msgs else "",
    }


async def _persist_assistant_message(interview_id: int, content: str) -> int:
    """流式完成后落库 assistant 消息（独立会话，不占用请求事务）。"""
    async with AsyncSessionLocal() as db:
        msg = InterviewMessage(interview_id=interview_id, role="assistant", content=content)
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        return msg.id


def _chat_sse(interview_id: int, resume_text: str, job_position: str, history: list[dict]):
    """SSE 生成器：流式产出面试官问题，完成后落库。"""
    async def gen():
        chunks: list[str] = []
        try:
            async for text in stream_question(resume_text, job_position, history):
                chunks.append(text)
                yield _sse("delta", {"text": text})
            answer = "".join(chunks)
            if answer:
                msg_id = await _persist_assistant_message(interview_id, answer)
                yield _sse("done", {"interview_id": interview_id, "message_id": msg_id})
            else:
                yield _sse("error", {"detail": "AI 未返回内容，请重试"})
        except Exception as e:
            logger.exception("面试 SSE 生成失败 interview_id=%s", interview_id)
            yield _sse("error", {"detail": f"AI 生成失败：{e}"})
    return gen()


# ---- 创建会话：SSE 返回首题 ----
@router.post("", status_code=201)
async def create_interview(
    payload: InterviewCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    resume_text = ""
    if payload.resume_id:
        resume = await db.get(Resume, payload.resume_id)
        if not resume or resume.user_id != user.id:
            raise HTTPException(status_code=404, detail="简历不存在")
        if resume.parse_status.value != "completed":
            raise HTTPException(status_code=400, detail="该简历尚未完成解析")
        resume_text = _resume_to_text(resume)

    itv = MockInterview(
        user_id=user.id, resume_id=payload.resume_id, job_position=payload.job_position.strip()
    )
    db.add(itv)
    await db.commit()
    await db.refresh(itv)

    async def gen():
        # start 事件先告知 interview_id，前端据此可更新路由
        yield _sse("start", {"interview_id": itv.id, "job_position": itv.job_position})
        # 复用对话 SSE（无历史 → 第一题）
        async for event in _chat_sse(itv.id, resume_text, itv.job_position, []):
            yield event

    return StreamingResponse(gen(), media_type="text/event-stream", status_code=201)


# ---- 我的会话列表 ----
@router.get("", response_model=list[InterviewOut])
async def list_interviews(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    itvs = (
        await db.execute(
            select(MockInterview)
            .options(selectinload(MockInterview.messages))
            .where(MockInterview.user_id == user.id)
            .order_by(MockInterview.id.desc())
        )
    ).scalars().all()
    return [_to_out(i) for i in itvs]


# ---- 会话详情（消息 + 报告）----
@router.get("/{interview_id}", response_model=InterviewDetailOut)
async def get_interview(
    interview_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    itv = await _load_own_interview(db, interview_id, user)
    out = _to_out(itv)
    out["messages"] = [
        {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
        for m in itv.messages
    ]
    out["report"] = itv.report
    return out


# ---- 删除面试会话（级联删除消息） ----
@router.delete("/{interview_id}", status_code=204)
async def delete_interview(
    interview_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    itv = await _load_own_interview(db, interview_id, user)
    await db.delete(itv)
    await db.commit()


# ---- 对话：提交回答，SSE 流式返回追问 ----
@router.post("/{interview_id}/chat")
async def chat_interview(
    interview_id: int,
    payload: InterviewChatIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    itv = await _load_own_interview(db, interview_id, user)
    if itv.status != InterviewStatus.ongoing:
        raise HTTPException(status_code=400, detail="该面试已结束")

    # 用户消息先落库（两段式：LLM 流式期间不占用本事务连接）
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="回答内容不能为空")
    user_msg = InterviewMessage(interview_id=itv.id, role="user", content=content)
    db.add(user_msg)
    await db.commit()

    resume_text = ""
    if itv.resume_id:
        resume = await db.get(Resume, itv.resume_id)
        resume_text = _resume_to_text(resume)
    history = [{"role": m.role, "content": m.content} for m in itv.messages] + [
        {"role": "user", "content": content}
    ]

    return StreamingResponse(
        _chat_sse(itv.id, resume_text, itv.job_position, history),
        media_type="text/event-stream",
    )


# ---- 结束面试：生成评估报告 ----
@router.post("/{interview_id}/finish", response_model=InterviewDetailOut)
async def finish_interview(
    interview_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    itv = await _load_own_interview(db, interview_id, user)
    if itv.status != InterviewStatus.ongoing:
        raise HTTPException(status_code=400, detail="该面试已结束")
    if not itv.messages:
        raise HTTPException(status_code=400, detail="面试尚未开始，无法生成报告")

    history = [{"role": m.role, "content": m.content} for m in itv.messages]
    resume_text = ""
    if itv.resume_id:
        resume = await db.get(Resume, itv.resume_id)
        resume_text = _resume_to_text(resume)

    report = await generate_report(resume_text, itv.job_position, history)
    if not report:
        # 报告失败保持 ongoing，用户可重试
        raise HTTPException(status_code=500, detail="报告生成失败，请稍后重试")

    itv.report = report
    itv.status = InterviewStatus.completed
    await db.commit()

    itv = await _load_own_interview(db, interview_id, user)
    out = _to_out(itv)
    out["messages"] = [
        {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
        for m in itv.messages
    ]
    out["report"] = itv.report
    return out

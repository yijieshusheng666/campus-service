# AI 模拟面试（Mock Interview）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户选择自己的简历与目标岗位，与 AI 面试官多轮对话（SSE 流式），结束后生成结构化评估报告。

**Architecture:** 复用 `app/services/llm.py` 的 LLM 客户端构建与稳健 JSON 解析，新增 `services/interview.py`（面试官流式生成 + 评估报告）。API 层照搬订单模块模式（状态校验 + 权限校验），SSE 端点采用"两段式会话"：依赖注入的 db 完成校验与用户消息落库，流式生成器内部用独立 `AsyncSessionLocal` 落库 assistant 消息，避免长事务占用连接。

**Tech Stack:** FastAPI StreamingResponse(SSE) / LangChain astream / SQLAlchemy 2.0 async / alembic / pytest + aiosqlite(sqlite 内存库) / Vue3 + 原生 fetch 流式读取。

**Spec:** `docs/superpowers/specs/2026-08-27-platform-modules-design.md` 模块一。一处微调：report 字段用 JSON 列而非 Text（与 Resume.parsed_sections 的既有用法一致）。

---

## 文件结构

后端：
- Create: `backend/app/models/interview.py` — MockInterview + InterviewMessage
- Modify: `backend/app/models/__init__.py` — 导出新模型
- Create: `backend/alembic/versions/0007_add_interviews.py` — 建两张表
- Create: `backend/app/schemas/interview.py` — 请求/响应契约
- Create: `backend/app/services/interview.py` — LLM 面试官 + 评估报告
- Create: `backend/app/api/interviews.py` — 5 个端点
- Modify: `backend/app/api/__init__.py` — 注册路由
- Create: `backend/pytest.ini`、`backend/tests/__init__.py`、`backend/tests/conftest.py`、`backend/tests/test_interviews.py`
- Modify: `backend/requirements.txt` — 测试依赖

前端：
- Create: `frontend/src/api/interview.js` — REST + SSE fetch 工具
- Modify: `frontend/src/router/index.js` — 3 个路由
- Modify: `frontend/src/layout/MainLayout.vue` — 导航项（执行时读现有菜单结构，照现有模式添加"AI 面试"入口）
- Create: `frontend/src/views/interview/InterviewList.vue`、`InterviewChat.vue`、`InterviewReport.vue`

---

### Task 1: 测试基础设施

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/pytest.ini`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_smoke.py`

- [ ] **Step 1: 添加测试依赖**

`backend/requirements.txt` 末尾追加：

```
# ---- 测试 ----
pytest==8.3.4
pytest-asyncio==0.25.0
aiosqlite==0.20.0
```

- [ ] **Step 2: 创建 pytest 配置**

`backend/pytest.ini`：

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 3: 安装依赖**

Run: `cd backend && pip install -r requirements.txt`
Expected: Successfully installed（或 already satisfied）

- [ ] **Step 4: 创建 conftest**

`backend/tests/__init__.py` 空文件。`backend/tests/conftest.py`：

```python
"""测试夹具：sqlite 内存库 + httpx AsyncClient + 已登录客户端。

httpx 的 ASGITransport 不触发 app lifespan，因此不会触碰真实 MySQL
（import 阶段创建的 engine 是惰性连接，不产生实际连接）。
"""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# StaticPool：sqlite 内存库跨连接共享同一底层连接，否则每个 session 拿到的是空库
engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _override_get_db():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    """注册并携带 Bearer token 的客户端。"""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "tester", "email": "tester@test.com", "password": "pass1234"},
    )
    assert resp.status_code == 201, resp.text
    client.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
    yield client
```

- [ ] **Step 5: 写冒烟测试验证基建**

`backend/tests/test_smoke.py`：

```python
"""基建冒烟：健康检查 + 注册登录。"""


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_register_and_me(auth_client):
    resp = await auth_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "tester"
```

- [ ] **Step 6: 运行测试**

Run: `cd backend && python -m pytest -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/pytest.ini backend/tests/
git commit -m "test: 搭建 pytest + sqlite 内存库测试基建"
```

---

### Task 2: 数据模型 + 迁移

**Files:**
- Create: `backend/app/models/interview.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0007_add_interviews.py`

- [ ] **Step 1: 写模型**

`backend/app/models/interview.py`：

```python
"""AI 模拟面试模型：会话 + 多轮消息。"""
import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InterviewStatus(str, enum.Enum):
    ongoing = "ongoing"      # 进行中
    completed = "completed"  # 已结束（含评估报告）


class MockInterview(Base):
    __tablename__ = "mock_interviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    job_position: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[InterviewStatus] = mapped_column(
        Enum(InterviewStatus), default=InterviewStatus.ongoing, index=True
    )
    # 评估报告 JSON：overall_score / dimensions / strengths / weaknesses / suggestions
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    messages: Mapped[list["InterviewMessage"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan", order_by="InterviewMessage.id"
    )


class InterviewMessage(Base):
    __tablename__ = "interview_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("mock_interviews.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # assistant | user
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    interview: Mapped["MockInterview"] = relationship(back_populates="messages")
```

- [ ] **Step 2: 注册到模型包**

`backend/app/models/__init__.py` 改为：

```python
"""ORM 模型包。"""
from app.models.favorite import Favorite
from app.models.goods import Goods, GoodsImage
from app.models.interview import InterviewMessage, MockInterview
from app.models.order import Order
from app.models.resume import Resume
from app.models.user import User

__all__ = [
    "User", "Goods", "GoodsImage", "Favorite", "Resume", "Order",
    "MockInterview", "InterviewMessage",
]
```

- [ ] **Step 3: 写迁移**

`backend/alembic/versions/0007_add_interviews.py`：

```python
"""新增 AI 模拟面试表

Revision ID: 0007_add_interviews
Revises: 0006_add_resume_parse_status
Create Date: 2026-08-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_add_interviews"
down_revision: Union[str, None] = "0006_add_resume_parse_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mock_interviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resume_id",
            sa.Integer(),
            sa.ForeignKey("resumes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("job_position", sa.String(100), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ongoing", "completed", name="interviewstatus"),
            nullable=False,
            server_default="ongoing",
        ),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mock_interviews_user_id", "mock_interviews", ["user_id"])
    op.create_index("ix_mock_interviews_status", "mock_interviews", ["status"])

    op.create_table(
        "interview_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "interview_id",
            sa.Integer(),
            sa.ForeignKey("mock_interviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_interview_messages_interview_id", "interview_messages", ["interview_id"])


def downgrade() -> None:
    op.drop_table("interview_messages")
    op.drop_table("mock_interviews")
```

- [ ] **Step 4: 执行迁移**

Run: `cd backend && alembic upgrade head`
Expected: 无报错，数据库出现两张新表

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/interview.py backend/app/models/__init__.py backend/alembic/versions/0007_add_interviews.py
git commit -m "feat: AI 模拟面试数据模型与迁移"
```

---

### Task 3: LLM 面试服务

**Files:**
- Create: `backend/app/services/interview.py`
- Create: `backend/tests/test_interview_service.py`

- [ ] **Step 1: 写服务**

`backend/app/services/interview.py`：

```python
"""AI 模拟面试服务：面试官流式提问 + 结束评估报告。

复用 app/services/llm.py 的 LLM 客户端构建与稳健 JSON 解析。
"""
import logging
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.llm import _build_llm, _robust_json_parse

logger = logging.getLogger(__name__)

# 上下文裁剪：最多携带最近 N 轮（1 轮 = user + assistant）
MAX_HISTORY_ROUNDS = 10

INTERVIEWER_SYSTEM = """你是一位资深的技术面试官，正在对候选人进行{job_position}岗位的模拟面试。

【候选人简历】
{resume_text}

【面试规则】
1. 每次只提出一个问题，问题要基于简历内容与岗位要求，有针对性
2. 提问顺序参考真实面试：自我介绍开场 → 项目/经历深挖 → 技术基础 → 场景/开放题
3. 追问要深入：技术选型原因、量化数据来源、 STAR 各环节展开、踩坑与解决
4. 口吻专业、友好；不要一次抛出多个问题；不要输出与提问无关的内容
5. 不评价候选人的回答（评价在面试结束的评估报告环节进行）
"""

REPORT_SYSTEM = """你是资深面试官与职业教练，基于一场完整的模拟面试记录输出评估报告。
**只返回紧凑JSON（不要任何解释、markdown、多余换行缩进）**。

JSON结构（字段名不要改）：
{{"overall_score": 0到100整数, "dimensions": [{{"name": "维度名", "score": 0到100整数, "comment": "一句话评价"}}], "strengths": ["优势点", "..."], "weaknesses": ["短板", "..."], "suggestions": ["具体可执行的改进建议", "..."]}}

评估维度建议（可按实际内容取舍4-6个）：简历质量与岗位匹配度、项目深度与技术功底、表达逻辑与结构化、量化意识、技术基础、应变能力。
要求：strengths/weaknesses/suggestions 各 2-4 条，必须引用面试中的具体内容，禁止空泛套话；不得编造面试中未出现的信息。所有内容使用中文。
"""


def build_interview_messages(
    resume_text: str, job_position: str, history: list[dict]
) -> list:
    """构建 LLM 消息列表：system(简历+岗位) + 最近 N 轮历史。

    history 元素形如 {"role": "user"|"assistant", "content": str}。
    """
    msgs: list = [
        SystemMessage(content=INTERVIEWER_SYSTEM.format(
            job_position=job_position, resume_text=resume_text[:8000] or "（未提供简历）"
        ))
    ]
    recent = history[-MAX_HISTORY_ROUNDS * 2 :]
    for m in recent:
        content = str(m.get("content", ""))
        if m.get("role") == "user":
            msgs.append(HumanMessage(content=content))
        else:
            msgs.append(AIMessage(content=content))
    return msgs


async def stream_question(
    resume_text: str, job_position: str, history: list[dict]
) -> AsyncGenerator[str, None]:
    """流式生成面试官的下一个问题（逐段 yield 文本增量）。"""
    llm = _build_llm()
    msgs = build_interview_messages(resume_text, job_position, history)
    async for chunk in llm.astream(msgs):
        text = getattr(chunk, "text", None)
        if text := (text or "").strip() if isinstance(text, str) else "":
            yield text
        elif text is not None and text != "":
            yield text


async def generate_report(
    resume_text: str, job_position: str, history: list[dict]
) -> dict:
    """生成评估报告 dict，失败返回空 dict。"""
    llm = _build_llm()
    transcript = "\n\n".join(
        f"{'候选人' if m.get('role') == 'user' else '面试官'}：{m.get('content', '')}"
        for m in history
    )
    msgs = [
        SystemMessage(content=REPORT_SYSTEM),
        HumanMessage(
            content=f"【目标岗位】{job_position}\n\n【候选人简历】\n{resume_text[:6000] or '（未提供）'}\n\n【面试记录】\n{transcript[:12000]}"
        ),
    ]
    try:
        raw = await llm.ainvoke(msgs)
        text = raw.text if hasattr(raw, "text") else str(raw)
        report = _robust_json_parse(text)
        if not report or "overall_score" not in report:
            logger.warning("评估报告解析失败，原文起始: %s", str(text)[:300])
            return {}
        return report
    except Exception:
        logger.exception("评估报告生成失败")
        return {}
```

注意：`stream_question` 里的 chunk 处理要简化——不同 LLM 返回的 chunk.text 可能带空白，直接 yield 原文本（不 strip，避免吞空格）。修正实现为：

```python
async def stream_question(
    resume_text: str, job_position: str, history: list[dict]
) -> AsyncGenerator[str, None]:
    llm = _build_llm()
    msgs = build_interview_messages(resume_text, job_position, history)
    async for chunk in llm.astream(msgs):
        text = getattr(chunk, "text", "")
        if text:
            yield text
```

- [ ] **Step 2: 写单测（纯函数部分，不碰 LLM）**

`backend/tests/test_interview_service.py`：

```python
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
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && python -m pytest tests/test_interview_service.py -v`
Expected: 3 passed（注意：会实例化 LLM 客户端吗？不会——build_interview_messages 不调用 _build_llm）

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/interview.py backend/tests/test_interview_service.py
git commit -m "feat: AI 面试官 LLM 服务（流式提问+评估报告）"
```

---

### Task 4: schemas

**Files:**
- Create: `backend/app/schemas/interview.py`

- [ ] **Step 1: 写契约**

`backend/app/schemas/interview.py`：

```python
"""AI 模拟面试契约。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.interview import InterviewStatus


class InterviewCreate(BaseModel):
    resume_id: int | None = None
    job_position: str = Field(min_length=1, max_length=100)


class InterviewMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class InterviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resume_id: int | None
    job_position: str
    status: InterviewStatus
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_content: str = ""


class InterviewDetailOut(InterviewOut):
    messages: list[InterviewMessageOut] = []
    report: dict | None = None


class InterviewChatIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/interview.py
git commit -m "feat: 模拟面试 pydantic 契约"
```

---

### Task 5: API 端点 + 集成测试

**Files:**
- Create: `backend/app/api/interviews.py`
- Modify: `backend/app/api/__init__.py`
- Create: `backend/tests/test_interviews.py`

- [ ] **Step 1: 写 API**

`backend/app/api/interviews.py`：

```python
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
        parts = [f"姓名：{data.get('name') or resume.parsed_name or ''}",
                 f"求职意向：{data.get('job_title') or resume.parsed_job_title or ''}"]
        for sec in sections:
            parts.append(f"\n## {sec.get('title', '')}")
            for it in sec.get("items", []):
                head = " / ".join(x for x in (it.get("heading"), it.get("subheading"), it.get("date")) if x)
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

    return StreamingResponse(gen(), media_type="text/event-stream")


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
    user_msg = InterviewMessage(interview_id=itv.id, role="user", content=payload.content.strip())
    db.add(user_msg)
    await db.commit()

    resume_text = ""
    if itv.resume_id:
        resume = await db.get(Resume, itv.resume_id)
        resume_text = _resume_to_text(resume)
    history = [{"role": m.role, "content": m.content} for m in itv.messages] + [
        {"role": "user", "content": payload.content.strip()}
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
```

- [ ] **Step 2: 注册路由**

`backend/app/api/__init__.py` 改为：

```python
"""API 路由包。"""
from fastapi import APIRouter

from app.api import auth, favorites, goods, interviews, orders, resumes, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(goods.router)
api_router.include_router(favorites.router)
api_router.include_router(resumes.router)
api_router.include_router(orders.router)
api_router.include_router(interviews.router)
```

- [ ] **Step 3: 写集成测试（mock LLM 服务函数）**

`backend/tests/test_interviews.py`：

```python
"""模拟面试 API 集成测试：mock LLM 服务，验证流程/权限/状态机。"""
import json

import pytest


async def _fake_stream(resume_text, job_position, history):
    assert "后端" in job_position
    for chunk in ["请先", "自我介绍。"]:
        yield chunk


@pytest.fixture
def mock_llm(monkeypatch):
    monkeypatch.setattr("app.api.interviews.stream_question", _fake_stream)
    monkeypatch.setattr(
        "app.api.interviews.generate_report",
        lambda *a, **k: _fake_report(),
    )


async def _fake_report():
    return {
        "overall_score": 85,
        "dimensions": [{"name": "表达逻辑", "score": 80, "comment": "结构清晰"}],
        "strengths": ["项目经验扎实"],
        "weaknesses": ["量化不足"],
        "suggestions": ["补充数据"],
    }


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
    from app.database import get_db
    from app.main import app
    from app.models.resume import ParseStatus, Resume
    from tests.conftest import TestingSessionLocal

    # 直接在测试库造一份属于别人的简历
    async with TestingSessionLocal() as db:
        from app.models.user import User
        u = User(username="owner", email="owner@test.com", hashed_password="x")
        db.add(u)
        await db.commit()
        r = Resume(user_id=u.id, file_name="a.pdf", file_path="/x",
                   raw_text="别人", parse_status=ParseStatus.completed)
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
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过（注意 SSE 集成测试里 mock 的 `_persist_assistant_message` 使用 `AsyncSessionLocal`——它指向真实 MySQL！测试必须让该函数走测试库。在 conftest 中追加 override）

处理方式：conftest.py 追加（放 `app.dependency_overrides` 之后）：

```python
# 两段式落库使用 AsyncSessionLocal，测试环境重定向到测试库
import app.api.interviews as _interviews_mod

async def _test_persist(interview_id: int, content: str) -> int:
    async with TestingSessionLocal() as db:
        msg = _interviews_mod.InterviewMessage(
            interview_id=interview_id, role="assistant", content=content
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        return msg.id

_interviews_mod._persist_assistant_message = _test_persist
```

Run: `cd backend && python -m pytest -v`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/interviews.py backend/app/api/__init__.py backend/tests/test_interviews.py backend/tests/conftest.py
git commit -m "feat: 模拟面试 API（SSE 流式对话+评估报告）与集成测试"
```

---

### Task 6: 前端 API 层 + 路由 + 导航

**Files:**
- Create: `frontend/src/api/interview.js`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layout/MainLayout.vue`

- [ ] **Step 1: 写 API 层（含 SSE fetch 工具）**

`frontend/src/api/interview.js`：

```javascript
import request from './request'
import { useAuthStore } from '@/stores/auth'

export const myInterviews = () => request.get('/api/v1/interviews')
export const getInterview = (id) => request.get(`/api/v1/interviews/${id}`)
export const finishInterview = (id) => request.post(`/api/v1/interviews/${id}/finish`, {}, { timeout: 300000 })

/**
 * SSE 流式 POST（axios 不支持流式读取，用原生 fetch）。
 * onEvent(event, data) 依次回调 start/delta/done/error。
 */
export async function ssePost(url, body, onEvent) {
  const auth = useAuthStore()
  let resp
  try {
    resp = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(auth.token ? { Authorization: `Bearer ${auth.token}` } : {})
      },
      body: JSON.stringify(body)
    })
  } catch (e) {
    onEvent('error', { detail: '网络错误，请重试' })
    return
  }
  if (!resp.ok) {
    const detail = (await resp.json().catch(() => ({})))?.detail || `请求失败(${resp.status})`
    onEvent('error', { detail })
    return
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const raw = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      let event = 'message'
      let data = ''
      for (const line of raw.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim()
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (data) {
        try { onEvent(event, JSON.parse(data)) } catch { onEvent(event, { raw: data }) }
      }
    }
  }
}

export const createInterviewSse = (payload, onEvent) => ssePost('/api/v1/interviews', payload, onEvent)
export const chatInterviewSse = (id, content, onEvent) =>
  ssePost(`/api/v1/interviews/${id}/chat`, { content }, onEvent)
```

- [ ] **Step 2: 加路由**

`frontend/src/router/index.js` 的 MainLayout children 中（`favorites` 之后）添加：

```javascript
      {
        path: 'interviews',
        name: 'InterviewList',
        component: () => import('@/views/interview/InterviewList.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'interviews/:id',
        name: 'InterviewChat',
        component: () => import('@/views/interview/InterviewChat.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'interviews/:id/report',
        name: 'InterviewReport',
        component: () => import('@/views/interview/InterviewReport.vue'),
        meta: { requiresAuth: true }
      },
```

- [ ] **Step 3: 加导航**

读 `frontend/src/layout/MainLayout.vue`，按现有菜单项模式添加"AI 面试"入口（router-link 或 el-menu-item，指向 `/interviews`，与"二手/简历"入口同级）。

- [ ] **Step 4: 前端构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功（此时页面组件还未创建，先创建空页面或把本步骤与 Task 7 合并后执行）

实际上本步骤顺延到 Task 7 创建完页面后执行。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/interview.js frontend/src/router/index.js frontend/src/layout/MainLayout.vue
git commit -m "feat: 模拟面试前端 API 层(SSE)与路由导航"
```

---

### Task 7: 前端页面

**Files:**
- Create: `frontend/src/views/interview/InterviewList.vue`
- Create: `frontend/src/views/interview/InterviewChat.vue`
- Create: `frontend/src/views/interview/InterviewReport.vue`

- [ ] **Step 1: 会话列表页**

`frontend/src/views/interview/InterviewList.vue`：

```vue
<template>
  <div class="page">
    <div class="page-header">
      <h2>AI 模拟面试</h2>
      <el-button type="primary" @click="showCreate = true">开始新面试</el-button>
    </div>

    <el-empty v-if="!loading && !items.length" description="还没有面试记录，开始第一场吧" />
    <el-card v-for="it in items" :key="it.id" class="item" shadow="hover" @click="goChat(it)">
      <div class="item-row">
        <div class="info">
          <span class="pos">{{ it.job_position }}</span>
          <el-tag :type="it.status === 'ongoing' ? 'success' : 'info'" size="small">
            {{ it.status === 'ongoing' ? '进行中' : '已结束' }}
          </el-tag>
        </div>
        <div class="meta">
          <span>{{ it.message_count }} 条消息 · {{ formatTime(it.updated_at) }}</span>
        </div>
      </div>
      <div class="last">{{ it.last_content }}</div>
    </el-card>

    <el-dialog v-model="showCreate" title="开始新面试" width="420">
      <el-form label-width="70px">
        <el-form-item label="简历">
          <el-select v-model="form.resume_id" placeholder="可不选（通用面试）" clearable style="width: 100%">
            <el-option v-for="r in resumes" :key="r.id" :label="r.file_name" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标岗位">
          <el-input v-model="form.job_position" placeholder="如：Python 后端开发" maxlength="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :disabled="!form.job_position.trim()" :loading="creating" @click="create">
          开始面试
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { myInterviews, createInterviewSse } from '@/api/interview'
import { myResumes } from '@/api/resume'

const router = useRouter()
const items = ref([])
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const resumes = ref([])
const form = reactive({ resume_id: null, job_position: '' })

const load = async () => {
  loading.value = true
  try {
    const res = await myInterviews()
    items.value = res.data
  } finally {
    loading.value = false
  }
}

const loadResumes = async () => {
  try {
    const res = await myResumes()
    resumes.value = (res.data || []).filter((r) => r.parse_status === 'completed')
  } catch { /* 无简历时忽略 */ }
}

const create = async () => {
  creating.value = true
  let interviewId = null
  try {
    await createInterviewSse(
      { resume_id: form.resume_id || null, job_position: form.job_position.trim() },
      (event, data) => {
        if (event === 'start') interviewId = data.interview_id
        if (event === 'error') ElMessage.error(data.detail)
      }
    )
    if (interviewId) router.push({ name: 'InterviewChat', params: { id: interviewId } })
  } finally {
    creating.value = false
  }
}

const goChat = (it) => {
  router.push(
    it.status === 'completed'
      ? { name: 'InterviewReport', params: { id: it.id } }
      : { name: 'InterviewChat', params: { id: it.id } }
  )
}

const formatTime = (t) => new Date(t).toLocaleString('zh-CN', { hour12: false })

onMounted(() => { load(); loadResumes() })
</script>

<style scoped>
.page { max-width: 800px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.item { margin-bottom: 12px; cursor: pointer; }
.item-row { display: flex; justify-content: space-between; align-items: center; }
.pos { font-weight: 600; margin-right: 8px; }
.meta { color: var(--el-text-color-secondary); font-size: 13px; }
.last { margin-top: 8px; color: var(--el-text-color-secondary); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
```

注意：`myResumes()` 返回结构执行时核对（含 `parse_status` 字段即可用；若无该字段则不过滤直接展示）。

- [ ] **Step 2: 聊天页（核心：SSE 消费 + 打字机）**

`frontend/src/views/interview/InterviewChat.vue`：

```vue
<template>
  <div class="page">
    <div class="page-header">
      <h2>AI 模拟面试 · {{ detail?.job_position }}</h2>
      <el-button v-if="detail?.status === 'ongoing'" type="danger" plain :disabled="streaming" @click="finish">
        结束面试并生成报告
      </el-button>
      <el-button v-else type="primary" @click="goReport">查看评估报告</el-button>
    </div>

    <div ref="chatBox" class="chat-box">
      <div v-for="m in messages" :key="m.id ?? 'tmp'" class="bubble" :class="m.role">
        <div class="name">{{ m.role === 'assistant' ? '面试官' : '我' }}</div>
        <div class="content">{{ m.content }}</div>
      </div>
      <div v-if="streaming && pending" class="bubble assistant">
        <div class="name">面试官</div>
        <div class="content">{{ pending }}</div>
      </div>
    </div>

    <div class="input-row">
      <el-input
        v-model="input" type="textarea" :rows="3" placeholder="输入你的回答…"
        :disabled="streaming || detail?.status !== 'ongoing'" @keydown.enter.exact.prevent="send"
      />
      <el-button type="primary" :loading="streaming" :disabled="!input.trim() || detail?.status !== 'ongoing'" @click="send">
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { chatInterviewSse, finishInterview, getInterview } from '@/api/interview'

const route = useRoute()
const router = useRouter()
const detail = ref(null)
const messages = ref([])
const input = ref('')
const streaming = ref(false)
const pending = ref('')
const chatBox = ref(null)

const load = async () => {
  const res = await getInterview(route.params.id)
  detail.value = res.data
  messages.value = res.data.messages || []
  scrollToBottom()
}

const send = async () => {
  const content = input.value.trim()
  if (!content || streaming.value) return
  input.value = ''
  messages.value.push({ role: 'user', content })
  streaming.value = true
  pending.value = ''
  scrollToBottom()
  await chatInterviewSse(route.params.id, content, (event, data) => {
    if (event === 'delta') { pending.value += data.text; scrollToBottom() }
    else if (event === 'done') {
      messages.value.push({ role: 'assistant', content: pending.value })
      pending.value = ''
    } else if (event === 'error') {
      ElMessage.error(data.detail)
      if (pending.value) messages.value.push({ role: 'assistant', content: pending.value })
      pending.value = ''
    }
  })
  streaming.value = false
  scrollToBottom()
}

const finish = async () => {
  streaming.value = true
  try {
    await finishInterview(route.params.id)
    goReport()
  } catch { /* 拦截器已提示 */ } finally {
    streaming.value = false
  }
}

const goReport = () => router.push({ name: 'InterviewReport', params: { id: route.params.id } })

const scrollToBottom = async () => {
  await nextTick()
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
}

onMounted(load)
</script>

<style scoped>
.page { max-width: 800px; margin: 0 auto; display: flex; flex-direction: column; height: calc(100vh - 120px); }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.chat-box { flex: 1; overflow-y: auto; padding: 12px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; background: #fafafa; }
.bubble { max-width: 75%; margin-bottom: 14px; }
.bubble.user { margin-left: auto; }
.bubble.user .content { background: var(--el-color-primary); color: #fff; }
.bubble.assistant .content { background: #fff; border: 1px solid var(--el-border-color-lighter); }
.name { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.content { padding: 10px 12px; border-radius: 8px; white-space: pre-wrap; line-height: 1.6; }
.input-row { display: flex; gap: 12px; margin-top: 12px; align-items: flex-end; }
.input-row .el-textarea { flex: 1; }
</style>
```

- [ ] **Step 3: 报告页**

`frontend/src/views/interview/InterviewReport.vue`：

```vue
<template>
  <div v-if="report" class="page">
    <div class="page-header">
      <h2>面试评估报告 · {{ detail.job_position }}</h2>
      <el-button @click="$router.push({ name: 'InterviewList' })">返回列表</el-button>
    </div>

    <el-card class="score-card">
      <div class="overall">
        <div class="number">{{ report.overall_score }}</div>
        <div class="label">综合得分 / 100</div>
      </div>
    </el-card>

    <el-card class="section">
      <template #header>维度评分</template>
      <div v-for="d in report.dimensions" :key="d.name" class="dim">
        <span class="dim-name">{{ d.name }}</span>
        <el-progress :percentage="d.score" :stroke-width="12" style="flex: 1; margin: 0 16px" />
        <span class="dim-score">{{ d.score }}</span>
      </div>
      <div v-for="d in report.dimensions" :key="'c' + d.name" class="dim-comment">
        {{ d.name }}：{{ d.comment }}
      </div>
    </el-card>

    <div class="grid">
      <el-card class="section">
        <template #header>优势</template>
        <ul><li v-for="s in report.strengths" :key="s">{{ s }}</li></ul>
      </el-card>
      <el-card class="section">
        <template #header>短板</template>
        <ul><li v-for="w in report.weaknesses" :key="w">{{ w }}</li></ul>
      </el-card>
    </div>

    <el-card class="section">
      <template #header>改进建议</template>
      <ol><li v-for="s in report.suggestions" :key="s">{{ s }}</li></ol>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getInterview } from '@/api/interview'

const route = useRoute()
const detail = ref({})
const report = ref(null)

onMounted(async () => {
  const res = await getInterview(route.params.id)
  detail.value = res.data
  report.value = res.data.report
})
</script>

<style scoped>
.page { max-width: 800px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.score-card { text-align: center; margin-bottom: 16px; }
.overall .number { font-size: 48px; font-weight: 700; color: var(--el-color-primary); }
.overall .label { color: var(--el-text-color-secondary); }
.section { margin-bottom: 16px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.dim { display: flex; align-items: center; margin-bottom: 8px; }
.dim-name { width: 110px; }
.dim-score { width: 36px; text-align: right; }
.dim-comment { color: var(--el-text-color-secondary); font-size: 13px; margin-bottom: 4px; }
ul, ol { padding-left: 20px; line-height: 1.8; margin: 0; }
@media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
</style>
```

- [ ] **Step 4: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功无报错

- [ ] **Step 5: 手动端到端验证**

启动后端 `cd backend && uvicorn app.main:app --reload`，启动前端 `cd frontend && npm run dev`，浏览器验证：
1. 登录 → 导航到"AI 面试" → 新建（选简历+岗位）→ 首题流式打出
2. 多轮问答 → 结束面试 → 报告页展示
3. 返回列表，进入已完成会话 → 直达报告

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/interview/
git commit -m "feat: 模拟面试前端三页面（列表/SSE聊天/报告）"
```

---

### Task 8: 收尾

**Files:**
- Modify: `backend/app/main.py`（description 增加 AI 模拟面试一行）
- Modify: `README.md`（新增模块功能描述，遵循"README 严格反映实际功能"原则）

- [ ] **Step 1: main.py description 追加**

在 description 中 `- AI 简历：...` 之后添加：

```
- AI 模拟面试：选简历+岗位 → LLM 面试官多轮提问（SSE 流式）→ 结构化评估报告
```

- [ ] **Step 2: README 增加模块小节**

按现有 README 结构添加"AI 模拟面试"功能描述（三句话以内：入口、流程、报告）。

- [ ] **Step 3: 全量测试**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py README.md
git commit -m "docs: README 与 API 描述补充 AI 模拟面试模块"
```

---

## Self-Review 结论

- **Spec 覆盖**：设计文档模块一的功能范围（创建/多轮/流式/报告/回看）、数据模型、5 个接口、错误处理（403/400/500 保持 ongoing 可重试）、前端 3 页、测试要点全部有对应任务
- **占位符**：仅两处依赖执行时核对现有结构（MainLayout 菜单模式、myResumes 返回字段），均标注了核对方式，非功能缺口
- **类型一致性**：`InterviewOut.message_count/last_content` 在 API `_to_out` 与 schema、前端列表页使用一致；SSE 事件 start/delta/done/error 在后端 `_sse` 与前端 `ssePost` 解析一致
- **已知风险**：`_persist_assistant_message` 默认指向真实 MySQL，集成测试通过 conftest 覆写为测试库（Task 5 Step 4 已处理）

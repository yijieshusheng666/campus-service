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

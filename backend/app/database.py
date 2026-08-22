"""异步数据库：SQLAlchemy 2.0 Async + MySQL(asyncmy)。"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.sqlalchemy_url,
    echo=settings.DB_ECHO,
    # 关闭 pre_ping：asyncmy 的 ping() 需要 reconnect 参数，与当前 SQLAlchemy 方言不兼容会报错
    pool_pre_ping=False,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：提供一个事务级 AsyncSession。"""
    async with AsyncSessionLocal() as session:
        yield session
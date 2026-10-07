import os
from typing import Optional
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from cloudag.models.state import Base


def normalize_database_url(url: Optional[str] = None) -> str:
    db_url = url or os.getenv("DATABASE_URL", "sqlite+aiosqlite:///cloudag.db")
    if db_url.startswith("sqlite:///"):
        db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return db_url


def create_engine_and_sessionmaker(
    db_url: Optional[str] = None,
    echo: bool = False,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    normalized_url = normalize_database_url(db_url)
    connect_args = {}
    engine_kwargs = {
        "echo": echo,
        "future": True,
    }

    if "sqlite" in normalized_url:
        connect_args["check_same_thread"] = False
        if ":memory:" in normalized_url:
            engine_kwargs["poolclass"] = StaticPool

    engine = create_async_engine(
        normalized_url,
        connect_args=connect_args,
        **engine_kwargs,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    return engine, session_factory


async def init_db(engine: AsyncEngine) -> None:
    """Initializes tables for SQLite/PostgreSQL."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

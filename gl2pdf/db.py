"""
db.py
-----
Async SQLAlchemy engine + ORM model for api_keys table.

Required env vars
-----------------
DB_URL  e.g. mysql+aiomysql://user:pass@host:3306/gl2pdf
        If not set the app falls back to SQLite (useful for local dev).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import (
    Boolean, DateTime, Integer, String, Text,
    func, select, update, delete,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ── Engine ────────────────────────────────────────────────────────────────────

_DB_URL: str = os.environ.get(
    "DB_URL",
    "sqlite+aiosqlite:///./gl2pdf.db",   # dev fallback
)

_engine = create_async_engine(
    _DB_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    _engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


# ── ORM base & model ──────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class ApiKey(Base):
    __tablename__ = "api_keys"

    id:          Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:        Mapped[str]           = mapped_column(String(128), nullable=False)
    key_hash:    Mapped[str]           = mapped_column(String(256), nullable=False, unique=True)
    key_prefix:  Mapped[str]           = mapped_column(String(8),  nullable=False)   # first 8 chars for display
    is_active:   Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)
    created_at:  Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at:  Mapped[datetime|None] = mapped_column(DateTime, nullable=True, default=None)
    last_used_at:Mapped[datetime|None] = mapped_column(DateTime, nullable=True, default=None)
    use_count:   Mapped[int]           = mapped_column(Integer, default=0, nullable=False)


# ── Lifecycle ─────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create tables if they don't exist (idempotent)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession."""
    async with AsyncSessionLocal() as session:
        yield session


# ── Repository helpers ────────────────────────────────────────────────────────

async def get_all_keys(session: AsyncSession) -> list[ApiKey]:
    result = await session.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
    return list(result.scalars().all())


async def get_key_by_id(session: AsyncSession, key_id: int) -> ApiKey | None:
    return await session.get(ApiKey, key_id)


async def create_key(
    session: AsyncSession,
    name: str,
    key_hash: str,
    key_prefix: str,
    expires_at: datetime | None,
) -> ApiKey:
    obj = ApiKey(
        name=name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        expires_at=expires_at,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def rename_key(session: AsyncSession, key_id: int, new_name: str) -> bool:
    result = await session.execute(
        update(ApiKey).where(ApiKey.id == key_id).values(name=new_name)
    )
    await session.commit()
    return result.rowcount > 0


async def toggle_key(session: AsyncSession, key_id: int, active: bool) -> bool:
    result = await session.execute(
        update(ApiKey).where(ApiKey.id == key_id).values(is_active=active)
    )
    await session.commit()
    return result.rowcount > 0


async def delete_key(session: AsyncSession, key_id: int) -> bool:
    result = await session.execute(delete(ApiKey).where(ApiKey.id == key_id))
    await session.commit()
    return result.rowcount > 0


async def find_active_key(session: AsyncSession, key_hash: str) -> ApiKey | None:
    """Return the ApiKey row if hash matches, key is active, and not expired."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active == True,  # noqa: E712
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    if row.expires_at and row.expires_at.replace(tzinfo=timezone.utc) < now:
        return None
    return row


async def record_usage(session: AsyncSession, key_id: int) -> None:
    await session.execute(
        update(ApiKey).where(ApiKey.id == key_id).values(
            last_used_at=datetime.now(timezone.utc),
            use_count=ApiKey.use_count + 1,
        )
    )
    await session.commit()

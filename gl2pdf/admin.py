"""
admin.py
--------
/admin/keys  CRUD endpoints (protected by admin bearer token).

All routes require the Authorization: Bearer <ADMIN_TOKEN> header.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .auth import hash_key, require_admin
from .db import (
    AsyncSession,
    create_key,
    delete_key,
    get_all_keys,
    get_key_by_id,
    get_session,
    rename_key,
    toggle_key,
)

router = APIRouter(prefix="/admin", tags=["admin"])

# ── Pydantic schemas ──────────────────────────────────────────────────────────

class KeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    expires_at: datetime | None = Field(
        default=None,
        description="ISO-8601 UTC datetime. Leave null for no expiry.",
    )


class KeyRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class KeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    is_active: bool
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    use_count: int

    model_config = {"from_attributes": True}


class KeyCreated(KeyResponse):
    """Returned only on creation — includes the raw key (shown once)."""
    raw_key: str


# ── Helper ────────────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/keys", response_model=list[KeyResponse], summary="List all API keys")
async def list_keys(
    _: Annotated[None, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> list[KeyResponse]:
    rows = await get_all_keys(session)
    return [KeyResponse.model_validate(r) for r in rows]


@router.post(
    "/keys",
    response_model=KeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
    description=(
        "Generates a cryptographically random API key. "
        "**The raw key is returned only in this response — store it immediately.**"
    ),
)
async def create_api_key(
    body: KeyCreate,
    _: Annotated[None, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> KeyCreated:
    raw = secrets.token_urlsafe(32)          # 256-bit random key
    prefix = raw[:8]
    hashed = hash_key(raw)

    row = await create_key(
        session=session,
        name=body.name,
        key_hash=hashed,
        key_prefix=prefix,
        expires_at=body.expires_at,
    )
    return KeyCreated(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        is_active=row.is_active,
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        use_count=row.use_count,
        raw_key=raw,
    )


@router.patch("/keys/{key_id}/rename", response_model=KeyResponse, summary="Rename a key")
async def rename_api_key(
    key_id: int,
    body: KeyRename,
    _: Annotated[None, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> KeyResponse:
    ok = await rename_key(session, key_id, body.name)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found.")
    row = await get_key_by_id(session, key_id)
    return KeyResponse.model_validate(row)


@router.patch("/keys/{key_id}/activate", response_model=KeyResponse, summary="Activate a key")
async def activate_key(
    key_id: int,
    _: Annotated[None, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> KeyResponse:
    ok = await toggle_key(session, key_id, active=True)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found.")
    return KeyResponse.model_validate(await get_key_by_id(session, key_id))


@router.patch("/keys/{key_id}/deactivate", response_model=KeyResponse, summary="Deactivate a key")
async def deactivate_key(
    key_id: int,
    _: Annotated[None, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> KeyResponse:
    ok = await toggle_key(session, key_id, active=False)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found.")
    return KeyResponse.model_validate(await get_key_by_id(session, key_id))


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a key")
async def delete_api_key(
    key_id: int,
    _: Annotated[None, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> None:
    ok = await delete_key(session, key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found.")

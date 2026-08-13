"""
auth.py
-------
FastAPI dependencies for API key authentication.

How it works
------------
1. Client sends:  X-API-Key: <raw_key>
2. We hash the raw key with SHA-256 (fast, no salt needed for lookup).
3. We look up the hash in the DB; if found, active, and not expired → OK.
4. We record last_used_at + use_count in the background.

Admin endpoints use a separate bearer token from ADMIN_TOKEN env var.
"""

from __future__ import annotations

import hashlib
import logging
import os

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from .db import AsyncSession, find_active_key, get_session, record_usage

logger = logging.getLogger("gl2pdf.auth")

# ── Config ────────────────────────────────────────────────────────────────────

ADMIN_TOKEN: str = os.environ.get("ADMIN_TOKEN", "")

# ── Schemes ───────────────────────────────────────────────────────────────────

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer_scheme  = HTTPBearer(auto_error=False)

# ── Helpers ───────────────────────────────────────────────────────────────────

def hash_key(raw: str) -> str:
    """SHA-256 hex digest of the raw API key."""
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Dependencies ──────────────────────────────────────────────────────────────

async def require_api_key(
    raw_key: str | None = Security(_api_key_header),
    session: AsyncSession = Depends(get_session),
) -> None:
    """
    FastAPI dependency — raises 401/403 if the request carries no valid API key.
    Attach with:  Depends(require_api_key)
    """
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    key_hash = hash_key(raw_key)
    row = await find_active_key(session, key_hash)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid, expired, or inactive API key.",
        )

    # Fire-and-forget usage recording (best effort, don't fail the request)
    try:
        await record_usage(session, row.id)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to record API key usage for key id=%s", row.id, exc_info=True)


async def require_admin(
    creds: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> None:
    """
    FastAPI dependency — raises 401/403 if the request doesn't carry the
    admin bearer token set via ADMIN_TOKEN env var.
    """
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin access is not configured (ADMIN_TOKEN env var not set).",
        )

    if creds is None or creds.credentials != ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

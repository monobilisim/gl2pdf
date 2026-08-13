"""
api.py
------
FastAPI web application.

Endpoints
---------
GET  /healthz          → liveness probe (no auth)
GET  /readyz           → readiness probe (no auth)
POST /convert          → JSON body → PDF  (requires X-API-Key, auto-detects report type)
*    /admin/keys       → CRUD for API keys (requires admin token)

Environment variables
---------------------
DB_URL          SQLAlchemy async URL  (default: sqlite+aiosqlite:///./gl2pdf.db)
ADMIN_TOKEN     Bearer token for /admin/* routes
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import Response

from . import __version__
from .admin import router as admin_router
from .auth import require_api_key
from .db import init_db

# ── Logging ───────────────────────────────────────────────────────────────────
# Plain stdout logging (kubectl logs friendly). basicConfig() is a no-op if the
# root logger already has handlers (e.g. configured by the process manager).

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("gl2pdf")

# ── Limits ────────────────────────────────────────────────────────────────────
# ponytail: Content-Length check only (no streaming limit) — good enough for an
# internal CI tool where clients always send Content-Length; add streaming
# enforcement if a chunked-upload client shows up.
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 20 * 1024 * 1024))  # 20 MB

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="gl2pdf",
    description="Convert GitLab JSON reports (SAST, Code Quality) to PDF",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(admin_router)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting up — connecting to database...")
    try:
        # ponytail: 10s bound so a bad DB_URL fails loudly instead of hanging
        # silently past the liveness probe (was the CrashLoopBackOff root cause).
        await asyncio.wait_for(init_db(), timeout=10)
    except asyncio.TimeoutError:
        logger.error("Database connection timed out after 10s — check DB_URL / network reachability.")
        raise
    except Exception:
        logger.exception("Database initialization failed")
        raise
    logger.info("Database ready.")


# ── Probes (no auth) ──────────────────────────────────────────────────────────

@app.get("/healthz", tags=["probe"], status_code=200)
def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/readyz", tags=["probe"], status_code=200)
def readyz() -> dict:
    return {"status": "ready"}


# ── Convert (requires valid API key) ─────────────────────────────────────────

@app.post(
    "/convert",
    tags=["convert"],
    response_class=Response,
    dependencies=[Depends(require_api_key)],
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Generated PDF report"},
        401: {"description": "Missing X-API-Key header"},
        403: {"description": "Invalid, expired, or inactive API key"},
        400: {"description": "Invalid or unsupported JSON payload"},
        500: {"description": "Internal rendering error"},
    },
    summary="Convert GitLab JSON report → PDF",
    description=(
        "Post a raw GitLab SAST or Code Quality JSON report as the request body. "
        "Report type is auto-detected. "
        "Returns a PDF file (`application/pdf`). "
        "Requires a valid `X-API-Key` header."
    ),
)
async def convert(
    request: Request,
    title: str | None = None,
    repo: str | None = None,
    lang: str = "en",
) -> Response:
    # 1. Read & parse body ─────────────────────────────────────────────────────
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Request body exceeds {MAX_UPLOAD_BYTES} byte limit.",
        )

    body = await request.body()
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Request body is empty.")
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Request body exceeds {MAX_UPLOAD_BYTES} byte limit.",
        )

    try:
        raw = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid JSON: {exc}") from exc

    # 2. Detect report type ────────────────────────────────────────────────────
    if isinstance(raw, dict) and "vulnerabilities" in raw:
        report_type = "sast"
    elif isinstance(raw, list) and raw and "check_name" in raw[0]:
        report_type = "codequality"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unrecognized report format. Expected a GitLab SAST or Code Quality JSON.",
        )

    # 3. Write to temp file and parse ──────────────────────────────────────────
    with tempfile.NamedTemporaryFile(suffix=".json", mode="wb", delete=False) as tmp:
        tmp.write(body)
        tmp_path = Path(tmp.name)

    try:
        if report_type == "sast":
            from .parser import load as sast_load
            report = sast_load(tmp_path)
        else:
            from .cq_parser import load as cq_load
            report = cq_load(tmp_path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    # 4. Render PDF ────────────────────────────────────────────────────────────
    try:
        if report_type == "sast":
            from .renderer import render_bytes_sast
            pdf_bytes = render_bytes_sast(report, title=title, repo=repo, lang=lang)
        else:
            from .cq_renderer import render_bytes_cq
            pdf_bytes = render_bytes_cq(report, title=title, repo=repo, lang=lang)
    except Exception as exc:  # noqa: BLE001
        logger.exception("PDF render error (report_type=%s)", report_type)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"PDF render error: {exc}") from exc

    # 5. Return PDF ────────────────────────────────────────────────────────────
    filename = "sast-report.pdf" if report_type == "sast" else "codequality-report.pdf"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Report-Type":       report_type,
        "X-Total-Findings":    str(report.total),
    }
    if report_type == "sast":
        headers.update({
            "X-Severity-Critical": str(report.severity_counts.get("Critical", 0)),
            "X-Severity-High":     str(report.severity_counts.get("High", 0)),
            "X-Severity-Medium":   str(report.severity_counts.get("Medium", 0)),
            "X-Severity-Low":      str(report.severity_counts.get("Low", 0)),
        })
    else:
        headers.update({
            "X-Severity-Major":  str(report.severity_counts.get("major", 0)),
            "X-Severity-Minor":  str(report.severity_counts.get("minor", 0)),
        })

    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)

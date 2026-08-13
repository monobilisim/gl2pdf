# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 – builder
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY gl2pdf/ ./gl2pdf/

RUN pip install --no-cache-dir --prefix=/install .


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 – runtime
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="gl2pdf" \
      org.opencontainers.image.description="GitLab SAST & Code Quality JSON → PDF converter API" \
      org.opencontainers.image.version="1.0.0"

COPY --from=builder /install /usr/local

RUN useradd -m -u 1001 appuser
USER appuser

WORKDIR /app

# ── Environment variables ─────────────────────────────────────────────────────
# DB_URL        SQLAlchemy async connection string
#               MySQL  : mysql+aiomysql://user:pass@host:3306/gl2pdf
#               SQLite : sqlite+aiosqlite:///./gl2pdf.db  (default, dev only)
#
# ADMIN_TOKEN   Bearer token required to access /admin/* endpoints.
#               Generate one with:  python -c "import secrets; print(secrets.token_urlsafe(32))"
# ─────────────────────────────────────────────────────────────────────────────
ENV DB_URL="sqlite+aiosqlite:////app/gl2pdf.db" \
    ADMIN_TOKEN=""

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')"

EXPOSE 8080

# Use 1 worker when SQLite (file lock); increase for MySQL
CMD ["uvicorn", "gl2pdf.api:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "1", \
     "--timeout-keep-alive", "75"]

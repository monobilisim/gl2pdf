# Development Guide

## Project structure

```
gl2pdf/
├── gl2pdf/
│   ├── __init__.py       # __version__, __author__
│   ├── __main__.py       # `python -m gl2pdf` entry point
│   ├── cli.py            # Click CLI: report-type detection, parsing, rendering, console output
│   ├── api.py             # FastAPI app: /healthz, /readyz, POST /convert
│   ├── admin.py           # /admin/keys CRUD router (API key management)
│   ├── auth.py             # X-API-Key and admin Bearer-token dependencies
│   ├── db.py               # Async SQLAlchemy engine + ApiKey ORM model
│   ├── parser.py           # SAST JSON → SastReport dataclass
│   ├── cq_parser.py        # Code Quality JSON → CqReport dataclass
│   ├── template.py         # HTML template for SAST PDFs (styling lives here)
│   ├── cq_template.py      # HTML template for Code Quality PDFs
│   ├── renderer.py         # ReportLab renderer for SAST reports
│   └── cq_renderer.py      # ReportLab renderer for Code Quality reports (handles 100K+ issues via splitByRow)
├── tests/
│   ├── conftest.py         # TestClient + isolated temp-SQLite fixtures
│   ├── test_smoke.py       # import/parser/CLI-version smoke tests
│   ├── test_api.py         # full API integration tests (auth, admin CRUD, /convert)
│   └── test_renderer.py    # renderer output tests (PDF magic bytes)
├── k8s/                     # Kubernetes manifests — see docs/DEPLOYMENT.md
├── docs/                     # This directory
├── Dockerfile                # Multi-stage build → ghcr.io/monobilisim/gl2pdf
├── pyproject.toml
└── .github/workflows/ci.yml  # test → build-binary (3 OS) → build-container (ghcr.io)
```

Both report types (SAST and Code Quality) follow the same pipeline shape: `*_parser.py` (JSON → dataclass) → `*_renderer.py` (draws the PDF directly with ReportLab). `*_template.py` supplies the localized labels, section text, and `SEVERITY_COLOR`/`SEVERITY_ORDER` constants that the renderer imports — its `build_html()` function is a leftover from the pre-ReportLab WeasyPrint era and is no longer called by the render path (nothing goes through HTML anymore, `--save-html` is correspondingly a no-op).

## Local setup

```bash
git clone git@github.com:monobilisim/gl2pdf.git
cd gl2pdf
python3 -m venv .venv
.venv/bin/pip install -e ".[test,dev]"
```

- `test` extra: `pytest`, `httpx` (required by FastAPI's `TestClient`)
- `dev` extra: `pyinstaller` (for building standalone binaries)

No system packages are required — rendering is pure-Python ReportLab (WeasyPrint, which needed Pango/Cairo, was replaced for ~25x faster large-report rendering).

### Running the CLI locally

```bash
.venv/bin/gl2pdf gl-sast-report.json --open
```

### Running the API locally

```bash
ADMIN_TOKEN=dev-token .venv/bin/python3 -m uvicorn gl2pdf.api:app --reload --port 8080
```

`DB_URL` defaults to a local `sqlite+aiosqlite:///./gl2pdf.db` file if unset — see [Configuration](CONFIGURATION.md).

## Tests

```bash
.venv/bin/python3 -m pytest tests/ -v
```

`tests/conftest.py` sets `DB_URL`/`ADMIN_TOKEN` to isolated temp values and reloads the `gl2pdf.api`/`admin`/`auth`/`db` modules before each test run, since the async DB engine is created at import time — this keeps tests fully isolated from any real database and from each other.

What's covered: module imports, SAST/Code Quality parsing, CLI `--version`, all `/admin/keys` CRUD + auth paths, `/convert` success and failure cases (missing/invalid/inactive key, empty/malformed/unrecognized body), and renderer output (`render_bytes_sast`/`render_bytes_cq` produce valid PDF bytes).

Not covered yet: actual PDF *content* verification (only that valid PDF bytes are produced), Dockerfile build, Kubernetes manifests, PyInstaller binaries. These are exercised structurally by CI (see below) but not asserted against expected output.

## Building a standalone binary locally

```bash
.venv/bin/pyinstaller --onefile --name gl2pdf gl2pdf/__main__.py
./dist/gl2pdf --version
```

CI builds this for linux-x64, macos-arm64, and windows-x64 on every push (see below).

## Building the Docker image locally

```bash
docker build -t gl2pdf:local .
docker run --rm -e ADMIN_TOKEN=dev-token -p 8080:8080 gl2pdf:local
```

The build is two-stage: an `gcc`/`libffi-dev` builder stage compiles wheels, and the runtime stage is a slim Python image with no build tools, running as a non-root `appuser`.

## CI (`.github/workflows/ci.yml`)

Three jobs, triggered on push to `main`, on `v*` tags, and on pull requests:

1. **`test`** — installs `.[test]`, runs `pytest -q`. All other jobs depend on this passing.
2. **`build-binary`** — matrix over `ubuntu-latest`/`macos-latest`/`windows-latest`, runs PyInstaller against `gl2pdf/__main__.py`, uploads each binary as a workflow artifact. On a `v*` tag push, binaries are additionally attached to a GitHub Release.
3. **`build-container`** — only on `push` events (not PRs, since it needs registry credentials), builds and pushes to `ghcr.io/monobilisim/gl2pdf` with tags `latest` (default branch) and semver (`X.Y.Z`, `X.Y`) on tags.

Check current status: `gh run list --repo monobilisim/gl2pdf` or the CI badge in the main README.

## Coding conventions

- Type hints throughout (`from __future__ import annotations`), Python 3.10+ syntax (`str | None` unions).
- Each module has a short docstring header explaining its single responsibility — keep new modules to one concern.
- Business logic in `auth.py`/`db.py`/`admin.py`/`api.py` stays framework-idiomatic FastAPI/SQLAlchemy; avoid adding abstraction layers these small modules don't need.
- English only in code, comments, and docs. The one intentional exception is the `lang="tr"` PDF report content itself in `template.py`/`cq_template.py` — that's a user-facing localization feature, not something to translate away.

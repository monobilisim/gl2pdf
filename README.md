# [![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![GPL-3.0 License][license-shield]][license-url]
[![CI][ci-shield]][ci-url]

<div align="center">
<a href="https://mono.tr/">
  <img src="https://r2.mono.tr/logo/Mono-Logo.svg" width="340"/>
</a>

<h2 align="center">gl2pdf</h2>
<b>gl2pdf</b> — Turn GitLab SAST & Code Quality scan results into clean, shareable PDF reports
</div>

---

## Table of Contents

- [Table of Contents](#table-of-contents)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [HTTP API](#http-api)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Documentation](#documentation)
- [Roadmap](#roadmap)
- [License](#license)

---

## Features

- Parses GitLab **SAST** (`gl-sast-report.json`) and **Code Quality** (`gl-code-quality-report.json`) JSON reports — type is auto-detected
- Generates a multi-page PDF with:
  - Cover page with optional title and repository name
  - Executive summary with severity breakdown
  - Top vulnerability types (top 15) and most affected files (top 20)
  - Full finding details sorted by severity
  - Context-aware recommendations
- English (default) and Turkish report output
- CLI and HTTP API modes
- API key authentication for the HTTP endpoint
- SQLite (default) or MySQL backend for API key storage
- Docker and Kubernetes ready

---

## Installation

Requires Python 3.10+. PDF rendering is done with ReportLab (pure Python, no system dependencies needed).

**Install from source:**
```bash
git clone https://github.com/monobilisim/gl2pdf
cd gl2pdf
pip install .
```

**Prebuilt binaries**

Standalone binaries (linux-x64, macos-arm64, windows-x64) are built on every push and attached to [GitHub Releases](https://github.com/monobilisim/gl2pdf/releases) for tagged versions.

```bash
curl -LO https://github.com/monobilisim/gl2pdf/releases/latest/download/gl2pdf-linux-x64
chmod +x gl2pdf-linux-x64
./gl2pdf-linux-x64 gl-sast-report.json
```

**Docker / GHCR**

A container image is published to GitHub Container Registry on every push to main and on tags.

```bash
docker pull ghcr.io/monobilisim/gl2pdf:latest
docker run --rm -e ADMIN_TOKEN=your-secret-token -p 8080:8080 ghcr.io/monobilisim/gl2pdf:latest
```

---

## Usage

### CLI

```bash
gl2pdf gl-sast-report.json
```

With options:
```bash
gl2pdf gl-sast-report.json \
  --title "My Project — Security Report" \
  --repo "myorg/myrepo" \
  --lang tr \
  -o report.pdf
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `-o`, `--output PATH` | Output PDF path | Same dir as input, `.pdf` extension |
| `--title TEXT` | Cover page title | Localized default |
| `--repo TEXT` | Repository / project name on the cover | — |
| `--lang [en\|tr]` | Report language | `en` |
| `-q`, `--quiet` | Suppress intro and summary console output | — |
| `--save-html` | *(deprecated, no-op with the ReportLab renderer)* | — |
| `--open` | Open the generated PDF after creation | — |
| `-V`, `--version` | Show version | — |

---

## HTTP API

### Running the server

```bash
ADMIN_TOKEN=your-secret-token uvicorn gl2pdf.api:app --host 0.0.0.0 --port 8080
```

**Environment variables:**

| Variable | Description | Default |
|----------|-------------|---------|
| `ADMIN_TOKEN` | Bearer token for `/admin/*` endpoints | *(required)* |
| `DB_URL` | SQLAlchemy async connection string | `sqlite+aiosqlite:///./gl2pdf.db` |

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/healthz` | — | Liveness probe |
| `GET` | `/readyz` | — | Readiness probe |
| `POST` | `/convert` | `X-API-Key` | Convert SAST or Code Quality JSON → PDF (type auto-detected) |
| `GET` | `/admin/keys` | `Bearer` | List API keys |
| `POST` | `/admin/keys` | `Bearer` | Create API key |
| `PATCH` | `/admin/keys/{id}/rename` | `Bearer` | Rename a key |
| `PATCH` | `/admin/keys/{id}/activate` | `Bearer` | Activate a key |
| `PATCH` | `/admin/keys/{id}/deactivate` | `Bearer` | Deactivate a key |
| `DELETE` | `/admin/keys/{id}` | `Bearer` | Delete a key |

### Creating an API key

```bash
curl -X POST http://localhost:8080/admin/keys \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-ci-key"}'
```

### Converting a report

```bash
curl -X POST http://localhost:8080/convert \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  --data-binary @gl-sast-report.json \
  -o report.pdf
```

With optional query parameters:
```bash
curl -X POST "http://localhost:8080/convert?title=My+Project&repo=myorg/myrepo&lang=tr" \
  -H "X-API-Key: your-api-key" \
  --data-binary @gl-sast-report.json \
  -o report.pdf
```

Interactive API docs available at `/docs` (Swagger UI) and `/redoc`.

---

## Kubernetes Deployment

Manifests are provided in the `k8s/` directory. The setup uses Traefik `IngressRoute`.

> For full step-by-step instructions — including database setup (SQLite vs MySQL), generating the admin token, and creating your first API key — see [**docs/DEPLOYMENT.md**](docs/DEPLOYMENT.md).

### Steps

1. **Use the published image:**
   CI publishes `ghcr.io/monobilisim/gl2pdf` automatically (`latest` on main, `vX.Y.Z` semver on tags). The manifests in `k8s/` already reference it.

   Custom builds are still possible:
   ```bash
   docker build -t ghcr.io/monobilisim/gl2pdf:custom .
   ```

2. **Fill in `k8s/secret.yaml`:**
   ```yaml
   stringData:
     ADMIN_TOKEN: "your-admin-token"
     DB_URL: "mysql+aiomysql://user:pass@host:3306/gl2pdf"
   ```

3. **Update the domain in `k8s/ingressroute.yaml`** if needed.

4. **Deploy:**
   ```bash
   kubectl apply -f k8s/
   ```

5. **Verify:**
   ```bash
   kubectl -n gl2pdf get pods
   curl https://gl2pdf.yourdomain.com/healthz
   ```

---

## Documentation

This README covers the basics. For details, see the docs in [`docs/`](docs/):

| Doc | Covers |
|-----|--------|
| [CLI.md](docs/CLI.md) | Full CLI reference — every flag, examples, exit codes |
| [API.md](docs/API.md) | Full HTTP API reference — auth, `/convert`, `/admin/keys`, curl examples |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Environment variables (`ADMIN_TOKEN`, `DB_URL`), SQLite vs MySQL |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Kubernetes deployment — DB setup, secrets, apply order, verification |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Project structure, running tests, building binaries/images, CI, conventions |
| [GITLAB_CI.md](docs/GITLAB_CI.md) | Example `.gitlab-ci.yml` — convert SAST/Code Quality reports to PDF in your pipeline |

---

## Roadmap

- **Multi-tenant architecture** — organization-based API key isolation, per-tenant branding (logo, colors, report language), tenant self-service portal
- **Web UI** — admin panel for managing tenants, API keys, and viewing conversion logs

---

## License

gl2pdf is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE) file for details.

[contributors-shield]: https://img.shields.io/github/contributors/monobilisim/gl2pdf.svg?style=for-the-badge
[contributors-url]: https://github.com/monobilisim/gl2pdf/graphs/contributors
[ci-shield]: https://img.shields.io/github/actions/workflow/status/monobilisim/gl2pdf/ci.yml?branch=main&style=for-the-badge
[ci-url]: https://github.com/monobilisim/gl2pdf/actions/workflows/ci.yml
[forks-shield]: https://img.shields.io/github/forks/monobilisim/gl2pdf.svg?style=for-the-badge
[forks-url]: https://github.com/monobilisim/gl2pdf/network/members
[stars-shield]: https://img.shields.io/github/stars/monobilisim/gl2pdf.svg?style=for-the-badge
[stars-url]: https://github.com/monobilisim/gl2pdf/stargazers
[issues-shield]: https://img.shields.io/github/issues/monobilisim/gl2pdf.svg?style=for-the-badge
[issues-url]: https://github.com/monobilisim/gl2pdf/issues
[license-shield]: https://img.shields.io/github/license/monobilisim/gl2pdf.svg?style=for-the-badge
[license-url]: https://github.com/monobilisim/gl2pdf/blob/main/LICENSE

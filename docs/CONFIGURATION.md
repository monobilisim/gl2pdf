# Configuration Reference

Environment variables read by the HTTP API (`gl2pdf.api:app`). The CLI takes all its configuration as flags — see [CLI Reference](CLI.md) — and reads none of these.

## Variables

| Variable | Required | Default | Used by |
|----------|----------|---------|---------|
| `ADMIN_TOKEN` | Only for `/admin/*` | *(unset)* | `gl2pdf/auth.py` |
| `DB_URL` | no | `sqlite+aiosqlite:///./gl2pdf.db` | `gl2pdf/db.py` |
| `MAX_UPLOAD_BYTES` | no | `20971520` (20 MB) | `gl2pdf/api.py` |

### `ADMIN_TOKEN`

Bearer token required for every `/admin/*` route (API key CRUD). If unset, `/admin/*` returns `503 Service Unavailable` instead of allowing unauthenticated access — the API is safe by default, but you must set this before the admin API is usable.

Generate a strong random value:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

This is a separate credential from the per-client `X-API-Key` values used for `/convert` — `ADMIN_TOKEN` controls who can create/revoke those API keys, not who can convert reports.

### `DB_URL`

SQLAlchemy async connection string for the API key store. Tables are created automatically on startup (`init_db()` runs in `@app.on_event("startup")`), so no migration step is needed — for MySQL you only need to create the empty database itself first, not the schema.

**SQLite** (default, good for local dev / single-replica deployments):

```
sqlite+aiosqlite:///./gl2pdf.db
sqlite+aiosqlite:////absolute/path/gl2pdf.db
```

SQLite is a local file — it does **not** work correctly with more than one running instance/replica pointed at the same path (or with separate ephemeral filesystems per pod, as in Kubernetes without a shared PVC). This is why the Dockerfile's default `CMD` uses `--workers 1`, and why the Kubernetes deployment guide recommends either MySQL or `replicas: 1` + a persistent volume.

**MySQL** (recommended for anything beyond a single instance):

```
mysql+aiomysql://user:pass@host:3306/gl2pdf
```

The `aiomysql` driver is already a declared dependency (`pyproject.toml`), no extra install needed.

### `MAX_UPLOAD_BYTES`

Maximum request body size, in bytes, accepted by `POST /convert`. Requests over the limit are rejected with `413 Request Entity Too Large` — checked against the `Content-Length` header before the body is read, and again against the actual body size as a fallback.

Default is `20971520` (20 MB), chosen to stay comfortably inside the container's memory limit (`resources.limits.memory: 1Gi` in `k8s/deployment.yaml`) even after accounting for JSON parsing and PDF rendering overhead on top of the raw upload. Raise it only if you also raise the container memory limit — the two are meant to be tuned together, see [Deployment Guide](DEPLOYMENT.md).

## Per-environment defaults

| Environment | `DB_URL` default | Where it's set |
|-------------|-------------------|-----------------|
| Local (`uvicorn gl2pdf.api:app`) | `sqlite+aiosqlite:///./gl2pdf.db` (code default) | Not set — falls through to the code default in `gl2pdf/db.py` |
| Docker image | `sqlite+aiosqlite:////app/gl2pdf.db` | `ENV DB_URL=...` in the `Dockerfile` |
| Kubernetes | Whatever you put in `k8s/secret.yaml` | `stringData.DB_URL`, injected via `secretKeyRef` (`gl2pdf-secret`) in `k8s/deployment.yaml` |

`ADMIN_TOKEN` has no code-level default in any of these — it must always be set explicitly wherever the API runs, or `/admin/*` stays disabled.

## Rendering options (not environment variables)

Report title, repository name, and language (`en`/`tr`) are **not** environment variables — they're per-request/per-invocation:

- CLI: `--title`, `--repo`, `--lang` flags (see [CLI Reference](CLI.md))
- API: `title`, `repo`, `lang` query parameters on `POST /convert` (see [API Reference](API.md))

## See also

- [API Reference](API.md) — endpoints that consume these variables
- [Deployment Guide](DEPLOYMENT.md) — filling in `k8s/secret.yaml` and choosing SQLite vs MySQL for a real cluster

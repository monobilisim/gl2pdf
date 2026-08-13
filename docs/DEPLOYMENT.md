# Kubernetes Deployment Guide

This guide walks through deploying gl2pdf to Kubernetes using the manifests in [`k8s/`](../k8s/), including setting up the database before you apply anything.

## 1. Choose a database backend

gl2pdf stores API keys in a SQL database via async SQLAlchemy. The schema (the `api_keys` table) is created automatically on startup — you do **not** need to run migrations. You only need the database itself to exist and be reachable.

| Backend | `DB_URL` format | Good for |
|---|---|---|
| SQLite (default) | `sqlite+aiosqlite:///./gl2pdf.db` | Local dev / single-replica testing only |
| MySQL | `mysql+aiomysql://user:pass@host:3306/dbname` | Production |

**Important:** [`k8s/deployment.yaml`](../k8s/deployment.yaml) runs `replicas: 2` by default. SQLite is a local file — with 2+ pods each would get its own independent, out-of-sync file, so API keys created via one pod would be invisible to the other. If you stay on SQLite, set `replicas: 1`. For any real deployment, use MySQL.

### 1a. Create the MySQL database (recommended for production)

Run this once against your MySQL server:

```sql
CREATE DATABASE gl2pdf CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'gl2pdf'@'%' IDENTIFIED BY 'S3cr3t';
GRANT ALL PRIVILEGES ON gl2pdf.* TO 'gl2pdf'@'%';
FLUSH PRIVILEGES;
```

Your `DB_URL` will then be:

```
mysql+aiomysql://gl2pdf:S3cr3t@mysql-host:3306/gl2pdf
```

Tables are created automatically the first time a gl2pdf pod starts — nothing else to run.

## 2. Generate an admin token

`ADMIN_TOKEN` protects the `/admin/*` endpoints used to manage API keys. Generate a random one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Keep this value somewhere safe (password manager / secret store) — you'll need it to create API keys after deploying.

## 3. Fill in `k8s/secret.yaml`

Edit the `stringData` values (plain text — Kubernetes base64-encodes them automatically):

```yaml
stringData:
  ADMIN_TOKEN: "<value from step 2>"
  DB_URL: "mysql+aiomysql://gl2pdf:S3cr3t@mysql-host:3306/gl2pdf"
```

## 4. Update the domain

Edit the `Host()` match in [`k8s/ingressroute.yaml`](../k8s/ingressroute.yaml) to your real domain, and uncomment the `tls:` block if you're not relying on a global/wildcard cert.

## 5. Apply the manifests, in order

`namespace.yaml` must go first since every other manifest targets the `gl2pdf` namespace:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingressroute.yaml
```

(Or simply `kubectl apply -f k8s/` — Kubernetes tolerates the ordering here since `secret`/`deployment`/`service`/`ingressroute` all just reference the namespace, but applying `namespace.yaml` first avoids race-condition errors on a clean cluster.)

The deployment pulls `ghcr.io/monobilisim/gl2pdf:latest`, which CI publishes automatically on every push to `main` (and as `vX.Y.Z` on tags).

## 6. Verify

```bash
kubectl -n gl2pdf get pods
kubectl -n gl2pdf logs -l app=gl2pdf --tail=50
curl https://gl2pdf.yourdomain.com/healthz
curl https://gl2pdf.yourdomain.com/readyz
```

Both probes should return `{"status": "ok"}` / `{"status": "ready"}`.

## 7. Create your first API key

```bash
curl -X POST https://gl2pdf.yourdomain.com/admin/keys \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-ci-key"}'
```

The response includes `raw_key` — this is shown **only once**. Store it now; only its hash is kept server-side. Use it as the `X-API-Key` header when calling `POST /convert`.

## Troubleshooting

- **Pods `CrashLoopBackOff`** — check `kubectl -n gl2pdf logs`. Most commonly `DB_URL` is unreachable (network policy / wrong host) or malformed.
- **`/admin/*` returns 503** — `ADMIN_TOKEN` is not set in the pod's environment; check the secret was applied and referenced correctly in `deployment.yaml`.
- **Large reports return `413`** — `POST /convert` caps request bodies at `MAX_UPLOAD_BYTES` (default 20 MB, see [Configuration](CONFIGURATION.md#max_upload_bytes)). This is intentionally well under the container's `resources.limits.memory: 1Gi` in `deployment.yaml`, so a large upload fails cleanly with `413` instead of the pod getting OOM-killed. If you need to accept bigger reports, raise both `MAX_UPLOAD_BYTES` and the memory limit together.
- **API keys "disappear" intermittently** — you're on SQLite with `replicas > 1`. Switch to MySQL or drop to a single replica.

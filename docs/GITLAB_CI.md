# Using gl2pdf in a GitLab CI/CD Pipeline

GitLab's built-in **SAST** and **Code Quality** scanners already produce
`gl-sast-report.json` / `gl-code-quality-report.json` as job artifacts. This
guide shows how to add a pipeline job that turns those artifacts into a PDF
report, so reviewers can download a readable document straight from the
pipeline instead of digging through the JSON or the Security tab.

This doc only covers **the gl2pdf-specific part** (the extra job). For how to
enable/configure the scanners themselves, see GitLab's own docs:

- SAST: <https://docs.gitlab.com/ee/user/application_security/sast/>
- Code Quality: <https://docs.gitlab.com/ee/ci/testing/code_quality.html>
- Report artifacts (`artifacts:reports:*`): <https://docs.gitlab.com/ee/ci/yaml/artifacts_reports.html>

The exact `include:` template paths and job names occasionally change
upstream — always check the linked GitLab docs for the current syntax for
*your* GitLab version; only the `gl2pdf` job below is something we maintain.

---

## How it works

1. A GitLab-provided job (`sast`, `code_quality`, etc.) runs and produces a
   JSON report as an artifact.
2. A `gl2pdf` job runs after it, `needs:` that job's artifact, and runs the
   CLI (`gl2pdf gl-sast-report.json -o sast-report.pdf`) against it.
3. The resulting PDF is uploaded as a pipeline artifact you can download from
   the **Pipeline → Jobs → Artifacts** view.

There are two ways to run the CLI in a job — pick one:

- **Docker image** (fastest, no install step) — use the image published to
  `ghcr.io/monobilisim/gl2pdf` as the job's `image:`.
- **pip install** — use a plain Python image and `pip install gl2pdf`.

If you already run gl2pdf as a persistent HTTP service (see
[API.md](API.md) / [DEPLOYMENT.md](DEPLOYMENT.md)), you can instead `curl`
the `/convert` endpoint from the CI job — useful if you don't want to spend
CI minutes installing dependencies on every run.

---

## Example: SAST report → PDF

```yaml
include:
  - template: Jobs/SAST.gitlab-ci.yml   # produces gl-sast-report.json — see GitLab SAST docs

sast-pdf:
  stage: test
  needs: ["semgrep-sast"]               # match this to whichever SAST job(s) your project runs
  image:
    name: ghcr.io/monobilisim/gl2pdf:latest
    entrypoint: [""]
  script:
    - gl2pdf gl-sast-report.json --repo "$CI_PROJECT_PATH" -o sast-report.pdf
  artifacts:
    paths:
      - sast-report.pdf
    expire_in: 30 days
  rules:
    - if: $CI_COMMIT_BRANCH
```

`needs: ["semgrep-sast"]` should list whichever SAST analyzer job(s) actually
run in your project (GitLab's SAST template can spawn several, e.g.
`semgrep-sast`, `gosec-sast`, `brakeman-sast` — see the SAST job list in your
own pipeline). `needs:` pulls in that job's artifacts without waiting for
the whole `test` stage.

---

## Example: Code Quality report → PDF

```yaml
include:
  - template: Code-Quality.gitlab-ci.yml   # produces gl-code-quality-report.json — see GitLab Code Quality docs

code-quality-pdf:
  stage: test
  needs: ["code_quality"]
  image:
    name: ghcr.io/monobilisim/gl2pdf:latest
    entrypoint: [""]
  script:
    - gl2pdf gl-code-quality-report.json --repo "$CI_PROJECT_PATH" -o code-quality-report.pdf
  artifacts:
    paths:
      - code-quality-report.pdf
    expire_in: 30 days
  rules:
    - if: $CI_COMMIT_BRANCH
```

---

## Both in one pipeline

```yaml
include:
  - template: Jobs/SAST.gitlab-ci.yml
  - template: Code-Quality.gitlab-ci.yml

.gl2pdf:
  image:
    name: ghcr.io/monobilisim/gl2pdf:latest
    entrypoint: [""]
  stage: test
  artifacts:
    expire_in: 30 days
  rules:
    - if: $CI_COMMIT_BRANCH

sast-pdf:
  extends: .gl2pdf
  needs: ["semgrep-sast"]
  script:
    - gl2pdf gl-sast-report.json --repo "$CI_PROJECT_PATH" --lang tr -o sast-report.pdf
  artifacts:
    paths: [sast-report.pdf]

code-quality-pdf:
  extends: .gl2pdf
  needs: ["code_quality"]
  script:
    - gl2pdf gl-code-quality-report.json --repo "$CI_PROJECT_PATH" --lang tr -o code-quality-report.pdf
  artifacts:
    paths: [code-quality-report.pdf]
```

`--lang tr` is optional — drop it (or set `--lang en`) for an English report.
Report type doesn't need to be specified: `gl2pdf` auto-detects SAST vs Code
Quality from the JSON shape.

---

## Alternative: `pip install` instead of the Docker image

If you'd rather not switch the job's base image:

```yaml
sast-pdf:
  stage: test
  needs: ["semgrep-sast"]
  image: python:3.12-slim
  before_script:
    - pip install --no-cache-dir gl2pdf
  script:
    - gl2pdf gl-sast-report.json -o sast-report.pdf
  artifacts:
    paths: [sast-report.pdf]
```

## Alternative: call a running gl2pdf API instead

```yaml
sast-pdf:
  stage: test
  needs: ["semgrep-sast"]
  image: curlimages/curl:latest
  script:
    - >
      curl -sf -X POST "$GL2PDF_URL/convert?repo=$CI_PROJECT_PATH"
      -H "X-API-Key: $GL2PDF_API_KEY"
      --data-binary @gl-sast-report.json
      -o sast-report.pdf
  artifacts:
    paths: [sast-report.pdf]
```

Set `GL2PDF_URL` and `GL2PDF_API_KEY` as CI/CD variables (mask the key). See
[API.md](API.md) for the full `/convert` reference.

---

## See also

- [CLI.md](CLI.md) — full `gl2pdf` CLI flag reference
- [API.md](API.md) — full HTTP API reference
- [DEPLOYMENT.md](DEPLOYMENT.md) — running gl2pdf as a service in Kubernetes
- GitLab SAST docs: <https://docs.gitlab.com/ee/user/application_security/sast/>
- GitLab Code Quality docs: <https://docs.gitlab.com/ee/ci/testing/code_quality.html>

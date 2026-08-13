# CLI Reference

`gl2pdf` converts a GitLab SAST or Code Quality JSON report into a PDF on the command line. Report type is auto-detected from the JSON shape — no flag needed.

## Install

```bash
pip install .          # from a repo checkout
# or grab a prebuilt binary — see the Installation section in the main README
```

## Basic usage

```bash
gl2pdf gl-sast-report.json
```

This writes `gl-sast-report.pdf` next to the input file.

## Options

```bash
gl2pdf INPUT_FILE [OPTIONS]
```

| Flag | Description | Default |
|------|-------------|---------|
| `-o`, `--output PATH` | Output PDF path | Same directory as `INPUT_FILE`, `.pdf` extension |
| `--title TEXT` | Report title shown on the cover page | Localized default |
| `--repo TEXT` | Repository / project name shown on the cover | — |
| `--lang [en\|tr]` | Report language | `en` |
| `-q`, `--quiet` | Suppress the intro panel and summary table | off |
| `--open` | Open the generated PDF with the system viewer after generation | off |
| `--save-html` | *(deprecated, no-op)* — HTML intermediate step was removed when the renderer switched from WeasyPrint to ReportLab | — |
| `-V`, `--version` | Print version and exit | — |
| `-h`, `--help` | Show help and exit | — |

## Examples

Auto-detected Code Quality report, Turkish output, custom title:

```bash
gl2pdf gl-code-quality-report.json \
  --lang tr \
  --title "Ana Şube — Kod Kalitesi Raporu" \
  --repo "myorg/myrepo" \
  -o kod-kalite-raporu.pdf
```

Quiet mode for scripting (no console output except errors):

```bash
gl2pdf gl-sast-report.json -q -o report.pdf && echo "done"
```

Open the PDF immediately after generation:

```bash
gl2pdf gl-sast-report.json --open
```

## Report type detection

`gl2pdf` inspects the parsed JSON structure, not the filename:

- A JSON **object** containing a `vulnerabilities` key → treated as a **SAST** report (`gl-sast-report.json` format).
- A JSON **array** whose first element has a `check_name` key → treated as a **Code Quality** report (`gl-code-quality-report.json` format).
- Anything else → the CLI exits with status `1` and prints an error explaining the expected formats.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | PDF generated successfully |
| `1` | Report type could not be detected, JSON failed to parse, or PDF rendering failed |

Errors are also printed with `[bold red]Error:[/bold red]` (or `Render error:`) styling via [rich](https://github.com/Textualize/rich) and go to stdout.

## What's in the PDF

Regardless of report type, the generated PDF includes:

- Cover page with optional title and repository name
- Executive summary with severity breakdown (counts + percentages)
- Top 15 finding types and top 20 most affected files
- Full finding details, sorted by severity
- Context-aware recommendations section

See also: [HTTP API reference](API.md) for the equivalent service-based workflow, and [Configuration](CONFIGURATION.md) for environment variables used by the API/Docker/Kubernetes deployments.

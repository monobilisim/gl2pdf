"""
cli.py
------
Command-line interface for gl2pdf.

Usage
-----
    gl2pdf report.json                      # auto-detects report type
    gl2pdf report.json -o /tmp/out.pdf      # explicit output path
    gl2pdf report.json --lang tr            # Turkish report
    gl2pdf report.json --save-html          # also keep intermediate HTML
    gl2pdf report.json --open               # open PDF after generation
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import box

from . import __version__

console = Console()

# ── Report type detection ─────────────────────────────────────────────────────

def _detect_report_type(path: Path) -> str:
    """Return 'sast' or 'codequality' based on JSON structure."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if isinstance(raw, dict) and "vulnerabilities" in raw:
        return "sast"
    if isinstance(raw, list) and raw and "check_name" in raw[0]:
        return "codequality"
    raise ValueError(
        "Unrecognized GitLab report format. "
        "Expected a SAST report (dict with 'vulnerabilities') "
        "or a Code Quality report (array with 'check_name')."
    )


# ── CLI definition ────────────────────────────────────────────────────────────

@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version")
@click.argument(
    "input_file",
    type=click.Path(exists=True, dir_okay=False, readable=True),
)
@click.option(
    "-o", "--output",
    default=None,
    metavar="PATH",
    help="Output PDF path. Default: same directory as INPUT_FILE with .pdf extension.",
)
@click.option(
    "--save-html",
    is_flag=True,
    default=False,
    help="Also save the intermediate HTML file next to the PDF.",
)
@click.option(
    "-q", "--quiet",
    is_flag=True,
    default=False,
    help="Suppress intro and summary output.",
)
@click.option(
    "--open",
    "open_after",
    is_flag=True,
    default=False,
    help="Open the generated PDF with the system viewer after generation.",
)
@click.option(
    "--title",
    default=None,
    metavar="TEXT",
    help="Report title shown on the cover.",
)
@click.option(
    "--repo",
    default=None,
    metavar="TEXT",
    help="Repository / project name shown on the cover.",
)
@click.option(
    "--lang",
    default="en",
    show_default=True,
    type=click.Choice(["en", "tr"], case_sensitive=False),
    help="Report language.",
)
def main(
    input_file: str,
    output: str | None,
    save_html: bool,
    quiet: bool,
    open_after: bool,
    title: str | None,
    repo: str | None,
    lang: str,
) -> None:
    """
    Convert a GitLab JSON report (SAST or Code Quality) to a professional PDF.

    INPUT_FILE  Path to the GitLab JSON report file. Report type is auto-detected.
    """
    input_path  = Path(input_file).resolve()
    output_path = Path(output).resolve() if output else input_path.with_suffix(".pdf")

    # 1. Detect report type ────────────────────────────────────────────────────
    try:
        report_type = _detect_report_type(input_path)
    except (ValueError, json.JSONDecodeError, KeyError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    if not quiet:
        console.print(
            Panel(
                f"[bold blue]gl2pdf[/bold blue] v{__version__}\n"
                f"Type  : [yellow]{report_type.upper()}[/yellow]\n"
                f"Input : [cyan]{input_path}[/cyan]\n"
                f"Output: [cyan]{output_path}[/cyan]",
                expand=False,
            )
        )

    # 2. Parse ─────────────────────────────────────────────────────────────────
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True, console=console) as progress:
        t = progress.add_task("Parsing JSON …", total=None)
        try:
            if report_type == "sast":
                from .parser import load as sast_load
                report = sast_load(input_path)
            else:
                from .cq_parser import load as cq_load
                report = cq_load(input_path)
        except (FileNotFoundError, ValueError) as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)
        progress.update(t, description="JSON parsed.")

    # 3. Print summary ─────────────────────────────────────────────────────────
    if not quiet:
        _print_summary(report, report_type)

    # 4. Render PDF ────────────────────────────────────────────────────────────
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True, console=console) as progress:
        t = progress.add_task("Rendering PDF …", total=None)
        try:
            if report_type == "sast":
                from .renderer import render_sast
                pdf_path = render_sast(report, output_path, title=title, repo=repo, lang=lang)
            else:
                from .cq_renderer import render_cq
                pdf_path = render_cq(report, output_path, title=title, repo=repo, lang=lang)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[bold red]Render error:[/bold red] {exc}")
            sys.exit(1)
        progress.update(t, description="PDF rendered.")

    # 5. Optionally save HTML (no longer applicable — ReportLab renders directly) ──
    if save_html:
        console.print(f"[dim]--save-html is not supported with ReportLab renderer (skipped)[/dim]")

    size_kb = pdf_path.stat().st_size // 1024
    console.print(
        f"\n[bold green]Done![/bold green]  "
        f"PDF saved → [cyan]{pdf_path}[/cyan]  "
        f"([dim]{size_kb} KB[/dim])"
    )

    # 7. Open PDF ──────────────────────────────────────────────────────────────
    if open_after:
        _open_file(pdf_path)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_summary(report, report_type: str) -> None:
    if report_type == "sast":
        from .parser import SastReport
        sev_order  = ["Critical", "High", "Medium", "Low", "Info", "Unknown"]
        sev_styles = {"Critical": "bold red", "High": "bold yellow",
                      "Medium": "yellow", "Low": "green", "Info": "cyan", "Unknown": "dim"}
        tbl = Table(title=f"SAST Summary  –  {report.source_file.name}",
                    box=box.ROUNDED, show_header=True, header_style="bold blue")
        tbl.add_column("Severity", style="bold", min_width=10)
        tbl.add_column("Count", justify="right", min_width=8)
        tbl.add_column("Share",  justify="right", min_width=8)
        for sev in sev_order:
            cnt = report.severity_counts.get(sev, 0)
            if cnt == 0:
                continue
            pct = cnt / report.total * 100 if report.total else 0
            tbl.add_row(sev, str(cnt), f"{pct:.1f}%", style=sev_styles.get(sev, ""))
    else:
        from .cq_parser import SEVERITY_ORDER
        sev_styles = {"blocker": "bold red", "critical": "bold red",
                      "major": "bold yellow", "minor": "yellow", "info": "cyan"}
        tbl = Table(title=f"Code Quality Summary  –  {report.source_file.name}",
                    box=box.ROUNDED, show_header=True, header_style="bold blue")
        tbl.add_column("Severity", style="bold", min_width=10)
        tbl.add_column("Count", justify="right", min_width=8)
        tbl.add_column("Share",  justify="right", min_width=8)
        for sev in SEVERITY_ORDER:
            cnt = report.severity_counts.get(sev, 0)
            if cnt == 0:
                continue
            pct = cnt / report.total * 100 if report.total else 0
            tbl.add_row(sev.upper(), str(cnt), f"{pct:.1f}%", style=sev_styles.get(sev, ""))

    tbl.add_section()
    tbl.add_row("[bold]TOTAL[/bold]", f"[bold]{report.total}[/bold]", "100.0%")
    console.print(tbl)
    console.print()


def _open_file(path: Path) -> None:
    try:
        if sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["start", str(path)], shell=True)
    except Exception:  # noqa: BLE001
        pass

"""
parser.py
---------
Loads and validates a GitLab SAST JSON report, then returns a
structured SastReport dataclass ready for rendering.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class Vulnerability:
    id: str
    name: str
    description: str
    severity: str
    file: str
    start_line: int | str
    cwe: list[str]
    owasp: list[str]
    scanner_id: str


@dataclass
class ScanInfo:
    analyzer_name: str
    analyzer_version: str
    scanner_name: str
    scanner_version: str


@dataclass
class SastReport:
    source_file: Path
    scan: ScanInfo
    vulnerabilities: list[Vulnerability]

    # pre-computed statistics (populated by _compute_stats)
    total: int = 0
    severity_counts: dict[str, int] = field(default_factory=dict)
    top_names: list[tuple[str, int]] = field(default_factory=list)
    top_files: list[tuple[str, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._compute_stats()

    def _compute_stats(self) -> None:
        self.total = len(self.vulnerabilities)
        self.severity_counts = dict(Counter(v.severity for v in self.vulnerabilities))
        self.top_names = Counter(v.name for v in self.vulnerabilities).most_common(15)
        self.top_files = Counter(v.file for v in self.vulnerabilities).most_common(20)

    def sorted_vulnerabilities(
        self,
        order: list[str] | None = None,
    ) -> list[Vulnerability]:
        """Return all vulnerabilities sorted by severity (most critical first)."""
        if order is None:
            order = ["Critical", "High", "Medium", "Low", "Info", "Unknown"]
        key = lambda v: order.index(v.severity) if v.severity in order else len(order)
        return sorted(self.vulnerabilities, key=key)


# ── Public loader ─────────────────────────────────────────────────────────────

def load(path: str | Path) -> SastReport:
    """Parse a GitLab SAST JSON file and return a SastReport."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    if path.suffix.lower() != ".json":
        raise ValueError(f"Expected a .json file, got: {path.name}")

    with open(path, "r", encoding="utf-8") as fh:
        raw: dict[str, Any] = json.load(fh)

    if "vulnerabilities" not in raw:
        raise ValueError(
            "The JSON file does not contain a 'vulnerabilities' key. "
            "Make sure it is a GitLab SAST report."
        )

    scan_raw = raw.get("scan", {})
    scan = ScanInfo(
        analyzer_name    = scan_raw.get("analyzer", {}).get("name", "Unknown"),
        analyzer_version = scan_raw.get("analyzer", {}).get("version", ""),
        scanner_name     = scan_raw.get("scanner", {}).get("name", "Unknown"),
        scanner_version  = scan_raw.get("scanner", {}).get("version", ""),
    )

    vulns = [_parse_vuln(v) for v in raw["vulnerabilities"]]

    return SastReport(source_file=path, scan=scan, vulnerabilities=vulns)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _parse_vuln(raw: dict[str, Any]) -> Vulnerability:
    loc = raw.get("location", {})
    identifiers = raw.get("identifiers", [])

    cwe   = [x["name"] for x in identifiers if x.get("type") == "cwe"]
    owasp = [x["name"] for x in identifiers if x.get("type") == "owasp"]

    return Vulnerability(
        id          = raw.get("id", ""),
        name        = raw.get("name", "Unknown"),
        description = raw.get("description", ""),
        severity    = raw.get("severity", "Unknown"),
        file        = loc.get("file", "—"),
        start_line  = loc.get("start_line", "—"),
        cwe         = cwe,
        owasp       = owasp,
        scanner_id  = raw.get("scanner", {}).get("id", ""),
    )

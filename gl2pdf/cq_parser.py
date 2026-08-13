"""
cq_parser.py
------------
Loads and validates a GitLab Code Quality JSON report, then returns a
structured CqReport dataclass ready for rendering.

GitLab Code Quality report format:
  A JSON array of issue objects, each with:
    - description : str
    - check_name  : str
    - fingerprint : str
    - severity    : "info" | "minor" | "major" | "critical" | "blocker"
    - location    : { path: str, lines: { begin: int } }
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SEVERITY_ORDER = ["blocker", "critical", "major", "minor", "info"]


@dataclass
class CqIssue:
    description: str
    check_name: str
    fingerprint: str
    severity: str
    path: str
    line: int
    engine_name: str = ""
    identifier: str = ""
    analyzer_version: str = ""
    content_body: str = ""

    @property
    def normalized_description(self) -> str:
        """Description suitable for grouping repeated analyzer messages."""
        return re.sub(r"\s+on\s+line\s+\d+\s*$", "", self.description, flags=re.IGNORECASE)


@dataclass
class CqReport:
    source_file: Path
    issues: list[CqIssue]

    total: int = 0
    severity_counts: dict[str, int] = field(default_factory=dict)
    top_checks: list[tuple[str, int]] = field(default_factory=list)
    top_descriptions: list[tuple[str, int]] = field(default_factory=list)
    top_files: list[tuple[str, int]] = field(default_factory=list)
    analyzer_counts: dict[str, int] = field(default_factory=dict)
    analyzer_versions: list[str] = field(default_factory=list)
    top_identifiers: list[tuple[str, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._compute_stats()

    def _compute_stats(self) -> None:
        self.total = len(self.issues)
        self.severity_counts = dict(Counter(i.severity for i in self.issues))
        self.top_checks = Counter(i.check_name for i in self.issues).most_common(15)
        self.top_descriptions = Counter(i.normalized_description for i in self.issues).most_common(15)
        self.top_files = Counter(i.path for i in self.issues).most_common(20)
        self.analyzer_counts = dict(Counter(i.engine_name or i.check_name.split(":", 1)[0] for i in self.issues))
        self.analyzer_versions = sorted({i.analyzer_version for i in self.issues if i.analyzer_version})
        self.top_identifiers = Counter(i.identifier or i.check_name for i in self.issues).most_common(15)

    @property
    def primary_analyzer(self) -> str | None:
        """Return the dominant analyzer/check name when all findings share one."""
        if len(self.analyzer_counts) == 1:
            return next(iter(self.analyzer_counts))
        return None

    @property
    def identifier_count(self) -> int:
        return len({i.identifier or i.check_name for i in self.issues if i.identifier or i.check_name})

    def sorted_issues(self) -> list[CqIssue]:
        key = lambda i: SEVERITY_ORDER.index(i.severity) if i.severity in SEVERITY_ORDER else len(SEVERITY_ORDER)  # noqa: E731
        return sorted(self.issues, key=key)


def load(path: str | Path) -> CqReport:
    """Parse a GitLab Code Quality JSON file and return a CqReport."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    if path.suffix.lower() != ".json":
        raise ValueError(f"Expected a .json file, got: {path.name}")

    with open(path, "r", encoding="utf-8") as fh:
        raw: Any = json.load(fh)

    if not isinstance(raw, list):
        raise ValueError("Code Quality report must be a JSON array.")

    issues = [_parse_issue(item) for item in raw]
    return CqReport(source_file=path, issues=issues)


def _parse_issue(raw: dict[str, Any]) -> CqIssue:
    loc = raw.get("location", {})
    lines = loc.get("lines", {})
    content = raw.get("content", {}) if isinstance(raw.get("content", {}), dict) else {}
    content_body = str(content.get("body", ""))
    check_name = raw.get("check_name", "unknown")
    engine_name = raw.get("engine_name", "") or check_name.split(":", 1)[0].strip()
    identifier = raw.get("identifier", "") or _extract_metadata(content_body, "Identifier")
    if not identifier and ":" in check_name:
        identifier = check_name.split(":", 1)[1].strip()
    return CqIssue(
        description = raw.get("description", ""),
        check_name  = check_name,
        fingerprint = raw.get("fingerprint", ""),
        severity    = raw.get("severity", "info").lower(),
        path        = loc.get("path", "—"),
        line        = lines.get("begin", 0),
        engine_name = engine_name,
        identifier  = identifier,
        analyzer_version = raw.get("analyzer_version", "") or _extract_metadata(content_body, "PHPStan Version") or _extract_metadata(content_body, "Analyzer Version"),
        content_body = content_body,
    )


def _extract_metadata(text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}\s*:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""

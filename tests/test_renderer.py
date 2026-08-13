from pathlib import Path


def test_render_sast_pdf_bytes():
    from gl2pdf.parser import SastReport, ScanInfo, Vulnerability
    from gl2pdf.renderer import render_bytes_sast

    report = SastReport(
        source_file=Path("sast.json"),
        scan=ScanInfo("Semgrep", "1.0", "GitLab SAST", "1.0"),
        vulnerabilities=[Vulnerability("1", "SQL Injection", "desc", "High", "app.py", 7, ["CWE-89"], [], "semgrep")],
    )
    assert render_bytes_sast(report).startswith(b"%PDF")


def test_render_code_quality_pdf_bytes():
    from gl2pdf.cq_parser import CqIssue, CqReport
    from gl2pdf.cq_renderer import render_bytes_cq

    report = CqReport(
        source_file=Path("cq.json"),
        issues=[CqIssue("Avoid long methods", "rubocop:Metrics/MethodLength", "abc", "major", "app.rb", 3)],
    )
    assert render_bytes_cq(report).startswith(b"%PDF")

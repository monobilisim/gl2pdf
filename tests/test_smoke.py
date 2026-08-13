import json

from click.testing import CliRunner


def test_imports():
    import gl2pdf
    import gl2pdf.cq_parser
    import gl2pdf.cq_renderer
    import gl2pdf.parser
    import gl2pdf.renderer


def test_parse_sast(tmp_path):
    path = tmp_path / "sast.json"
    path.write_text(json.dumps({
        "vulnerabilities": [{
            "id": "1",
            "name": "SQL Injection",
            "severity": "High",
            "location": {"file": "app.py", "start_line": 7},
        }]
    }), encoding="utf-8")

    from gl2pdf.parser import load

    report = load(path)
    assert report.total == 1
    assert report.vulnerabilities[0].name == "SQL Injection"
    assert report.severity_counts == {"High": 1}


def test_parse_code_quality(tmp_path):
    path = tmp_path / "cq.json"
    path.write_text(json.dumps([{
        "description": "Avoid long methods",
        "check_name": "rubocop:Metrics/MethodLength",
        "fingerprint": "abc",
        "severity": "major",
        "location": {"path": "app.rb", "lines": {"begin": 3}},
    }]), encoding="utf-8")

    from gl2pdf.cq_parser import load

    report = load(path)
    assert report.total == 1
    assert report.issues[0].check_name == "rubocop:Metrics/MethodLength"
    assert report.severity_counts == {"major": 1}


def test_cli_version():
    from gl2pdf.cli import main

    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0

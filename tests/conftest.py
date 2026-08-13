import asyncio
import importlib
import sys

import pytest
from fastapi.testclient import TestClient


ADMIN_TOKEN = "test-admin-token"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN_TOKEN)

    for name in ["gl2pdf.api", "gl2pdf.admin", "gl2pdf.auth", "gl2pdf.db"]:
        sys.modules.pop(name, None)

    api = importlib.import_module("gl2pdf.api")
    db = importlib.import_module("gl2pdf.db")
    asyncio.run(db.init_db())

    with TestClient(api.app) as test_client:
        yield test_client


@pytest.fixture()
def admin_headers():
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


@pytest.fixture()
def sast_payload():
    return {
        "scan": {
            "analyzer": {"name": "Semgrep", "version": "1.0"},
            "scanner": {"name": "GitLab SAST", "version": "1.0"},
        },
        "vulnerabilities": [{
            "id": "1",
            "name": "SQL Injection",
            "description": "Unsanitized SQL input",
            "severity": "High",
            "location": {"file": "app.py", "start_line": 7},
            "identifiers": [{"type": "cwe", "name": "CWE-89"}],
            "scanner": {"id": "semgrep"},
        }],
    }


@pytest.fixture()
def cq_payload():
    return [{
        "description": "Avoid long methods",
        "check_name": "rubocop:Metrics/MethodLength",
        "fingerprint": "abc",
        "severity": "major",
        "location": {"path": "app.rb", "lines": {"begin": 3}},
    }]

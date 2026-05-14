import io
import os
from pathlib import Path

import pytest
from fastapi import HTTPException

import main


def test_extract_text_rejects_unknown_extension():
    with pytest.raises(HTTPException) as exc:
        main.extract_text(b"hello", "resume.txt")
    assert exc.value.status_code == 400


def test_load_resume_bytes_http_success(monkeypatch):
    class DummyResponse:
        def __init__(self):
            self.content = b"abc"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(main.requests, "get", lambda url, timeout: DummyResponse())

    data = main.load_resume_bytes("https://example.com/resume.pdf")
    assert data == b"abc"


def test_load_resume_bytes_http_failure(monkeypatch):
    class DummyError(Exception):
        pass

    def raise_exc(url, timeout):
        raise main.requests.RequestException("boom")

    monkeypatch.setattr(main.requests, "get", raise_exc)

    with pytest.raises(HTTPException) as exc:
        main.load_resume_bytes("https://example.com/resume.pdf")
    assert exc.value.status_code == 502


def test_load_resume_bytes_local_disallowed(monkeypatch):
    monkeypatch.setattr(main, "REQUIRE_REMOTE_RESUME_URL", True)

    with pytest.raises(HTTPException) as exc:
        main.load_resume_bytes("C:/tmp/resume.pdf")
    assert exc.value.status_code == 400


def test_load_resume_bytes_local_missing_allowed(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "REQUIRE_REMOTE_RESUME_URL", False)

    with pytest.raises(HTTPException) as exc:
        main.load_resume_bytes(str(tmp_path / "missing.pdf"))
    assert exc.value.status_code == 404


def test_local_pdf_cv_extracts_text(monkeypatch):
    cv_path = Path(os.getenv("LOCAL_CV_TEST_PATH", r"D:\desktop\omar_fouda_cv.pdf"))
    if not cv_path.exists():
        pytest.skip(f"Local CV test file not found: {cv_path}")

    monkeypatch.setattr(main, "REQUIRE_REMOTE_RESUME_URL", False)

    content = main.load_resume_bytes(str(cv_path))
    text = main.extract_text(content, str(cv_path))

    assert len(content) > 0
    assert len(text) > 100
    assert "OMAR" in text.upper()


def test_resume_lookup_uses_configured_table_names(monkeypatch):
    captured = {}

    class DummyCursor:
        def execute(self, query, user_id):
            captured["query"] = query
            captured["user_id"] = user_id

        def fetchone(self):
            return ["https://example.com/resume.pdf"]

    class DummyConnection:
        def cursor(self):
            return DummyCursor()

        def close(self):
            return None

    monkeypatch.setattr(main, "get_app_db", lambda: DummyConnection())

    assert main.get_resume_path_by_user_id("user-1") == "https://example.com/resume.pdf"
    assert f"FROM {main.APPLICANT_TABLE} a" in captured["query"]
    assert f"JOIN {main.RESUME_TABLE} r" in captured["query"]

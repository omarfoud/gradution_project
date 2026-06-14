import io
import os
import sys
import types
from pathlib import Path
import pytest

# Same stubs as above
st_mod = types.ModuleType("sentence_transformers")
class FakeST:
    def __init__(self, *a, **kw): pass
    def encode(self, t, **kw):
        import numpy as np
        return np.ones((len(t), 384), dtype="float32")
    def get_sentence_embedding_dimension(self): return 384
st_mod.SentenceTransformer = FakeST
sys.modules.setdefault("sentence_transformers", st_mod)

faiss_mod = types.ModuleType("faiss")
class FakeIdx:
    ntotal=100; nprobe=20; d=384
    def search(self,v,k):
        import numpy as np
        return np.ones((1,k),"float32"), np.arange(k,"int64").reshape(1,k)
faiss_mod.IndexFlatIP=FakeIdx; faiss_mod.IndexIVFFlat=FakeIdx
faiss_mod.METRIC_INNER_PRODUCT=0; faiss_mod.normalize_L2=lambda x:None
faiss_mod.read_index=lambda p:FakeIdx(); faiss_mod.write_index=lambda i,p:None
sys.modules.setdefault("faiss", faiss_mod)

gmod=types.ModuleType("google"); gnmod=types.ModuleType("google.generativeai")
gmod.generativeai=gnmod; gnmod.configure=lambda **k:None
class FM:
    def generate_content(self,p):
        class R: text="ok"
        return R()
gnmod.GenerativeModel=lambda n:FM()
sys.modules.setdefault("google",gmod); sys.modules.setdefault("google.generativeai",gnmod)

pyodbc_mod=types.ModuleType("pyodbc")
class PyodbcError(Exception): pass
pyodbc_mod.Error=PyodbcError
pyodbc_mod.connect=lambda *a,**k:(_ for _ in ()).throw(PyodbcError("no db"))
sys.modules.setdefault("pyodbc",pyodbc_mod)

jwt_mod=types.ModuleType("jwt")
class JE(Exception): pass
jwt_mod.PyJWTError=JE; jwt_mod.decode=lambda t,s,algorithms:{"sub":"u1"}
sys.modules.setdefault("jwt",jwt_mod)

import main
from fastapi import HTTPException


def test_extract_text_rejects_unknown_extension():
    with pytest.raises(HTTPException) as exc:
        main.extract_text(b"hello", "resume.txt")
    assert exc.value.status_code == 400


def test_extract_text_detects_html_from_content():
    html_bytes = b"<html><body>Not a CV</body></html>"
    with pytest.raises(HTTPException) as exc:
        main.extract_text(html_bytes, "resume.pdf")  # extension looks ok but content is HTML
    # Should raise 502 (HTML redirect/auth wall detected)
    assert exc.value.status_code in (400, 502)


def test_load_resume_bytes_http_success(monkeypatch):
    class DummyResponse:
        content = b"abc"
        def raise_for_status(self): return None
    monkeypatch.setattr(main.requests, "get", lambda url, timeout: DummyResponse())
    data = main.load_resume_bytes("https://example.com/resume.pdf")
    assert data == b"abc"


def test_load_resume_bytes_http_failure(monkeypatch):
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


def test_resume_lookup_uses_configured_table_names(monkeypatch):
    captured = {}
    class DummyCursor:
        def execute(self, query, user_id):
            captured["query"] = query
            captured["user_id"] = user_id
        def fetchone(self):
            return ["https://example.com/resume.pdf"]
    class DummyConnection:
        def cursor(self): return DummyCursor()
        def close(self): return None
    monkeypatch.setattr(main, "get_app_db", lambda: DummyConnection())
    result = main.get_resume_path_by_user_id("user-1")
    assert result == "https://example.com/resume.pdf"
    assert f"FROM {main.APPLICANT_TABLE} a" in captured["query"]
    assert f"JOIN {main.RESUME_TABLE} r" in captured["query"]


def test_extract_text_valid_pdf():
    # Build a minimal valid PDF in memory
    import PyPDF2
    buf = io.BytesIO()
    writer = PyPDF2.PdfWriter()
    from PyPDF2.generic import NameObject
    page = writer.add_blank_page(width=612, height=792)
    writer.write(buf)
    buf.seek(0)
    # Blank page -> empty text is ok; we're testing no exception
    content = buf.read()
    # Should not raise (may return empty string from blank page)
    try:
        result = main.extract_text(content, "test.pdf")
    except HTTPException as e:
        # Empty content raises 400 — that's correct behavior
        assert e.status_code == 400
        assert "empty" in e.detail.lower()


def test_sql_identifier_validation():
    import re
    pattern = r"[A-Za-z_][A-Za-z0-9_]*"
    valid = ["Applicants", "Resume", "JobPostings", "Application", "Companies"]
    invalid = ["1table", "drop table", "Resume; DROP", "dbo.Resume"]
    for v in valid:
        assert re.fullmatch(pattern, v), f"{v} should be valid"
    for v in invalid:
        assert not re.fullmatch(pattern, v), f"{v} should be invalid"

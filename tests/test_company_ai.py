import os
os.environ["JWT_SECRET"] = "test-jwt-secret-key-1234567890-test"
os.environ["ADMIN_API_KEY"] = "test-admin-api-key-1234567890-test"
os.environ["TESTING"] = "true"

import asyncio
import httpx
import pytest
import sys
import types

# ---- Stub heavy dependencies ----
st_mod = types.ModuleType("sentence_transformers")
class FakeST:
    def __init__(self, *a, **kw): pass
    def encode(self, texts, **kw):
        import numpy as np
        return np.ones((len(texts), 384), dtype="float32")
    def get_sentence_embedding_dimension(self): return 384
st_mod.SentenceTransformer = FakeST
sys.modules.setdefault("sentence_transformers", st_mod)

faiss_mod = types.ModuleType("faiss")
class FakeIndex:
    def __init__(self, *a, **kw):
        self.ntotal = 100
        self.nprobe = 20
        self.d = 384
    def search(self, v, k):
        import numpy as np
        return np.ones((1,k), dtype="float32"), np.arange(k, dtype="int64").reshape(1,k)
    def add(self, vectors):
        self.ntotal += len(vectors)
faiss_mod.IndexFlatIP = FakeIndex
faiss_mod.IndexIVFFlat = FakeIndex
faiss_mod.METRIC_INNER_PRODUCT = 0
faiss_mod.normalize_L2 = lambda x: None
faiss_mod.read_index = lambda path: FakeIndex()
faiss_mod.write_index = lambda idx, path: None
faiss_mod.clone_index = lambda idx: idx
sys.modules.setdefault("faiss", faiss_mod)

genai_mod = types.ModuleType("google.generativeai")
google_mod = types.ModuleType("google")
google_mod.generativeai = genai_mod
genai_mod.configure = lambda **kw: None
class FakeModel:
    def generate_content(self, prompt): 
        class R: text = "ok"
        return R()
genai_mod.GenerativeModel = lambda name: FakeModel()
sys.modules.setdefault("google", google_mod)
sys.modules.setdefault("google.generativeai", genai_mod)

# Stub pyodbc
pyodbc_mod = types.ModuleType("pyodbc")
class PyodbcError(Exception): pass
pyodbc_mod.Error = PyodbcError

# Custom mock db cursor/conn
mock_cursor_data = {
    "fetchone_values": [],
    "fetchall_values": [],
}

class MockCursor:
    def execute(self, query, *args):
        pass
    def fetchone(self):
        if mock_cursor_data["fetchone_values"]:
            return mock_cursor_data["fetchone_values"].pop(0)
        return None
    def fetchall(self):
        if mock_cursor_data["fetchall_values"]:
            return mock_cursor_data["fetchall_values"].pop(0)
        return []

class MockConnection:
    def cursor(self):
        return MockCursor()
    def close(self):
        pass

pyodbc_mod.connect = lambda *a, **kw: MockConnection()
sys.modules.setdefault("pyodbc", pyodbc_mod)

# Stub jwt
jwt_mod = types.ModuleType("jwt")
class JWTError(Exception): pass
jwt_mod.PyJWTError = JWTError
jwt_decoded_payload = {"sub": "company_user_1"}
jwt_mod.decode = lambda token, secret, algorithms: jwt_decoded_payload
sys.modules.setdefault("jwt", jwt_mod)

import main

class SyncASGIClient:
    def __init__(self, app):
        self.app = app
    def get(self, url, **kwargs):
        return asyncio.run(self._request("GET", url, **kwargs))
    def post(self, url, **kwargs):
        return asyncio.run(self._request("POST", url, **kwargs))
    async def _request(self, method, url, **kwargs):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, url, **kwargs)

@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main, "generate_text", lambda prompt: "ok")
    monkeypatch.setattr(main, "REQUIRE_AUTH", True) # Force require auth for these tests
    monkeypatch.setattr(main.jwt, "decode", lambda token, secret, algorithms: {"sub": "company_user_1"})
    import pyodbc
    monkeypatch.setattr(pyodbc, "connect", lambda *a, **kw: MockConnection())
    yield SyncASGIClient(main.app)

def test_company_endpoints_unauthenticated_rejected(client):
    # Missing authorization header should yield 401
    res = client.post(
        "/chat/company/message",
        json={"company_user_id": "company_user_1", "message": "hello"}
    )
    assert res.status_code == 401

def test_company_endpoints_sub_mismatch_rejected(client):
    # JWT sub matches "company_user_1", but request company_user_id is "company_user_2"
    res = client.post(
        "/chat/company/message",
        json={"company_user_id": "company_user_2", "message": "hello"},
        headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 403

def test_company_context_success(client):
    # JWT sub is "company_user_1", and company_user_id is "company_user_1"
    # The database row returned has UserId = "company_user_1"
    mock_cursor_data["fetchone_values"] = [
        # Company context lookup row (CompanyID, Name, Industry, WebsiteURL, HeadquarterAddress, Location, LogoUrl, UserId)
        ("comp_1", "Acme", "Tech", "https://acme.com", "Main St", "Cairo", "https://acme.com/logo.png", "company_user_1"),
        # Applications count query
        (10,),
        # Status breakdown query fetchall
        # We need fetchall inside get_company_kpis status breakdown
    ]
    mock_cursor_data["fetchall_values"] = [
        [("Applied", 6), ("Interview", 4)], # Status rows
        [("job_1", "Data Engineer", 10)] # Top jobs rows
    ]

    res = client.post(
        "/chat/company/message",
        json={"company_user_id": "company_user_1", "message": "hello"},
        headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["company"]["company_id"] == "comp_1"
    assert body["company"]["user_id"] == "company_user_1"
    assert body["kpis"]["applications_count"] == 10
    assert body["kpis"]["status_breakdown"][0]["status"] == "Applied"
    assert body["kpis"]["top_jobs"][0]["job_id"] == "job_1"

def test_company_context_idor_mismatched_company_id_rejected(client):
    # JWT sub is "company_user_1", and company_user_id is "company_user_1"
    # But request supplies company_id = "comp_2"
    # The database company row returned for comp_2 has UserId = "company_user_other"
    mock_cursor_data["fetchone_values"] = [
        ("comp_2", "OtherCorp", "Finance", "https://other.com", "Second St", "Giza", None, "company_user_other")
    ]

    res = client.post(
        "/chat/company/message",
        json={"company_user_id": "company_user_1", "company_id": "comp_2", "message": "hello"},
        headers={"Authorization": "Bearer token"}
    )
    # The IDOR check should reject this request with 403 Forbidden!
    assert res.status_code == 403
    assert "access to this company context" in res.json()["detail"]

def test_company_analyze_company_idor_prevention(client):
    # IDOR check on /chat/company/analyze-company
    mock_cursor_data["fetchone_values"] = [
        ("comp_2", "OtherCorp", "Finance", "https://other.com", "Second St", "Giza", None, "company_user_other")
    ]
    res = client.post(
        "/chat/company/analyze-company",
        json={"company_user_id": "company_user_1", "company_id": "comp_2"},
        headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 403

def test_company_analyze_job_post_idor_prevention(client):
    # IDOR check on /chat/company/analyze-job-post
    mock_cursor_data["fetchone_values"] = [
        ("comp_2", "OtherCorp", "Finance", "https://other.com", "Second St", "Giza", None, "company_user_other")
    ]
    res = client.post(
        "/chat/company/analyze-job-post",
        json={"company_user_id": "company_user_1", "company_id": "comp_2", "job_posting_id": "job_1"},
        headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 403

def test_company_hiring_insights_idor_prevention(client):
    # IDOR check on /chat/company/hiring-insights
    mock_cursor_data["fetchone_values"] = [
        ("comp_2", "OtherCorp", "Finance", "https://other.com", "Second St", "Giza", None, "company_user_other")
    ]
    res = client.post(
        "/chat/company/hiring-insights",
        json={"company_user_id": "company_user_1", "company_id": "comp_2"},
        headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 403

def test_company_generate_job_post_idor_prevention(client):
    # IDOR check on /chat/company/generate-job-post
    mock_cursor_data["fetchone_values"] = [
        ("comp_2", "OtherCorp", "Finance", "https://other.com", "Second St", "Giza", None, "company_user_other")
    ]
    res = client.post(
        "/chat/company/generate-job-post",
        json={"company_user_id": "company_user_1", "company_id": "comp_2", "role": "Engineer"},
        headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 403

def test_company_find_candidates_idor_prevention(client):
    # IDOR check on /chat/company/find-candidates
    mock_cursor_data["fetchone_values"] = [
        ("comp_2", "OtherCorp", "Finance", "https://other.com", "Second St", "Giza", None, "company_user_other")
    ]
    res = client.post(
        "/chat/company/find-candidates",
        json={"company_user_id": "company_user_1", "company_id": "comp_2", "job_posting_id": "job_1"},
        headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 403


def test_company_context_idor_enforced_when_auth_disabled_but_token_provided(client, monkeypatch):
    # Even if REQUIRE_AUTH is False, if a token is provided (so sub is populated),
    # the IDOR check must still fire and reject mismatching company user ID
    monkeypatch.setattr(main, "REQUIRE_AUTH", False)
    mock_cursor_data["fetchone_values"] = [
        ("comp_2", "OtherCorp", "Finance", "https://other.com", "Second St", "Giza", None, "company_user_other")
    ]

    res = client.post(
        "/chat/company/message",
        json={"company_user_id": "company_user_1", "company_id": "comp_2", "message": "hello"},
        headers={"Authorization": "Bearer token"}
    )
    assert res.status_code == 403
    assert "access to this company context" in res.json()["detail"]


def test_company_endpoints_unauthenticated_allowed_when_auth_disabled(client, monkeypatch):
    # If REQUIRE_AUTH is False and no token is provided, access is allowed without auth check
    monkeypatch.setattr(main, "REQUIRE_AUTH", False)
    mock_cursor_data["fetchone_values"] = [
        ("comp_1", "Acme", "Tech", "https://acme.com", "Main St", "Cairo", "https://acme.com/logo.png", "company_user_1"),
        (10,),
    ]
    mock_cursor_data["fetchall_values"] = [
        [("Applied", 6), ("Interview", 4)],
        [("job_1", "Data Engineer", 10)]
    ]

    res = client.post(
        "/chat/company/message",
        json={"company_user_id": "company_user_1", "message": "hello"}
    )
    assert res.status_code == 200
    assert res.json()["company"]["company_id"] == "comp_1"

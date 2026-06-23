import os
os.environ["JWT_SECRET"] = "test-jwt-secret-key-1234567890-test"
os.environ["ADMIN_API_KEY"] = "test-admin-api-key-1234567890-test"
os.environ["TESTING"] = "true"

import asyncio
import httpx
import pytest
import sys
import types


# ---- Stub heavy dependencies that need real hardware ----
# Stub sentence_transformers
st_mod = types.ModuleType("sentence_transformers")
class FakeST:
    def __init__(self, *a, **kw): pass
    def encode(self, texts, **kw):
        import numpy as np
        return np.ones((len(texts), 384), dtype="float32")
    def get_sentence_embedding_dimension(self): return 384
st_mod.SentenceTransformer = FakeST
sys.modules["sentence_transformers"] = st_mod

# Stub faiss
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
sys.modules["faiss"] = faiss_mod

# Stub google.generativeai
genai_mod = types.ModuleType("google.generativeai")
google_mod = types.ModuleType("google")
google_mod.generativeai = genai_mod
genai_mod.configure = lambda **kw: None
class FakeModel:
    def generate_content(self, prompt): 
        class R: text = "ok"
        return R()
genai_mod.GenerativeModel = lambda name: FakeModel()
sys.modules["google"] = google_mod
sys.modules["google.generativeai"] = genai_mod

# Stub pyodbc
pyodbc_mod = types.ModuleType("pyodbc")
class PyodbcError(Exception): pass
pyodbc_mod.Error = PyodbcError
pyodbc_mod.connect = lambda *a, **kw: (_ for _ in ()).throw(PyodbcError("no real db"))
sys.modules["pyodbc"] = pyodbc_mod

# Stub jwt
jwt_mod = types.ModuleType("jwt")
class JWTError(Exception): pass
jwt_mod.PyJWTError = JWTError
jwt_mod.decode = lambda token, secret, algorithms: {"sub": "user1"}
sys.modules["jwt"] = jwt_mod

# Now safe to import main
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
    monkeypatch.setattr(
        main, "search_hybrid",
        lambda query_text, **kwargs: [{
            "job_id": 1, "faiss_id": 0, "title": "Data Scientist", "company": "ACME",
            "description": "", "qualifications": "", "responsibilities": "",
            "skills": "python", "experience": "junior", "location": "Cairo",
            "work_type": "remote", "salary_range": "", "similarity_score": 0.9,
        }],
    )
    def fake_resume_text(user_id):
        return "my resume"
    fake_resume_text.cache_clear = lambda: None
    monkeypatch.setattr(main, "get_resume_text_for_user", fake_resume_text)
    monkeypatch.setattr(main, "check_auth", lambda requested_id, auth_header: None)
    yield SyncASGIClient(main.app)


def test_health_ok(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "model_loaded" in body
    assert "index_loaded" in body


def test_clear_cache_ok(client):
    res = client.post("/clear-cache", headers={"X-Admin-API-Key": "test-admin-api-key-1234567890-test"})
    assert res.status_code == 200
    assert res.json()["status"] == "cache cleared"


def test_search_returns_jobs(client):
    res = client.post(
        "/search",
        json={"query": "python", "limit": 3, "location": None, "work_type": None, "experience": None},
    )
    assert res.status_code == 200
    body = res.json()
    assert "jobs" in body
    assert isinstance(body["jobs"], list)
    assert body["jobs"][0]["job_id"] == 1


def test_chat_returns_reply(client):
    res = client.post("/chat", json={"message": "hello"})
    assert res.status_code == 200
    assert res.json()["reply"] == "ok"


def test_recommend_matches_returns_summary_fields(client):
    res = client.post(
        "/recommend-matches",
        json={"user_id": "user-1", "location": None, "work_type": None, "experience": None, "limit": 5},
    )
    assert res.status_code == 200
    jobs = res.json()["jobs"]
    assert len(jobs) == 1
    assert set(jobs[0].keys()) == {
        "job_id", "title", "company", "location", "work_type",
        "experience", "salary_range", "similarity_score",
    }


def test_search_empty_query_rejected(client):
    res = client.post("/search", json={"query": "", "limit": 5})
    assert res.status_code == 422


def test_recommend_empty_user_id_rejected(client):
    res = client.post("/recommend-matches", json={"user_id": "", "limit": 5})
    assert res.status_code == 422


def test_chat_empty_message_rejected(client):
    res = client.post("/chat", json={"message": ""})
    assert res.status_code == 422


def test_keyword_match_score_prefers_relevant(monkeypatch):
    monkeypatch.setattr(main, "MODEL", None)
    job_text = "Python machine learning data preprocessing model evaluation"
    relevant  = "Python developer with machine learning, data preprocessing, model evaluation"
    unrelated = "Sales manager with customer service and retail operations"
    assert main.calculate_cv_match_score(job_text, relevant) > main.calculate_cv_match_score(job_text, unrelated)


def test_keyword_match_score_empty_inputs(monkeypatch):
    monkeypatch.setattr(main, "MODEL", None)
    assert main.calculate_cv_match_score("", "some resume") == 0
    assert main.calculate_cv_match_score("some job", "") == 0
    assert main.calculate_cv_match_score("", "") == 0


def test_keyword_match_score_range(monkeypatch):
    monkeypatch.setattr(main, "MODEL", None)
    score = main.calculate_cv_match_score("Python developer Flask REST API", "Python Flask REST API developer")
    assert 0 <= score <= 100


def test_health_fields_present(client):
    res = client.get("/health")
    body = res.json()
    expected_keys = {
        "status", "model_loaded", "index_loaded", "jobs_db_exists",
        "index_exists", "sql_server_configured", "gemini_configured",
        "require_remote_resume_url",
    }
    assert expected_keys.issubset(body.keys())


def test_upsert_job_embedding_writes_sqlite_and_index(monkeypatch, tmp_path):
    db_path = tmp_path / "jobs.db"
    index_path = tmp_path / "jobs.index"
    fake_index = FakeIndex()
    monkeypatch.setattr(main, "DB_PATH", str(db_path))
    monkeypatch.setattr(main, "INDEX_PATH", str(index_path))
    monkeypatch.setattr(main, "MODEL", FakeST())
    monkeypatch.setattr(main, "INDEX", fake_index)
    monkeypatch.setattr(main.faiss, "write_index", lambda index, path: index_path.write_text("index"))

    result = main.upsert_job_embedding({
        "job_id": 123,
        "title": "Backend Developer",
        "company": "Jobify",
        "description": "Build APIs",
        "qualifications": "Python",
        "responsibilities": "Develop services",
        "skills": "FastAPI SQL",
        "experience": "Junior",
        "location": "Cairo",
        "work_type": "Remote",
        "salary_range": "Negotiable",
    })

    assert result["job_id"] == 123
    assert result["faiss_id"] == 100
    assert result["index_total"] == 101
    conn = main.sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT job_id, faiss_id, title FROM jobs WHERE job_id = 123").fetchone()
    finally:
        conn.close()
    assert row == (123, 100, "Backend Developer")
    assert index_path.exists()


def test_upsert_job_embedding_accepts_guid_job_ids(monkeypatch, tmp_path):
    db_path = tmp_path / "jobs.db"
    index_path = tmp_path / "jobs.index"
    fake_index = FakeIndex()
    guid_job_id = "DA16524B-3634-4429-A1F0-4B8527100B79"
    monkeypatch.setattr(main, "DB_PATH", str(db_path))
    monkeypatch.setattr(main, "INDEX_PATH", str(index_path))
    monkeypatch.setattr(main, "MODEL", FakeST())
    monkeypatch.setattr(main, "INDEX", fake_index)
    monkeypatch.setattr(main.faiss, "write_index", lambda index, path: index_path.write_text("index"))

    result = main.upsert_job_embedding({
        "job_id": guid_job_id,
        "title": "Senior Interactions Architect",
        "company": "Lockman and Sons",
        "description": "<p>Design interaction systems</p>",
        "qualifications": None,
        "responsibilities": "<ul><li>Lead architecture</li></ul>",
        "skills": None,
        "experience": None,
        "location": "Antigua and Barbuda",
        "work_type": "[0]",
        "salary_range": "300.00 - 3000.00",
    })

    assert result["job_id"] == guid_job_id
    conn = main.sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT job_id, title, company FROM jobs WHERE job_id = ?", (guid_job_id,)).fetchone()
    finally:
        conn.close()
    assert row == (guid_job_id, "Senior Interactions Architect", "Lockman and Sons")

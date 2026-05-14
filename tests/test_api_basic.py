import asyncio

import httpx
import pytest

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
    # Avoid calling external services.
    monkeypatch.setattr(main, "generate_text", lambda prompt: "ok")

    # Avoid FAISS/SQLite dependency for endpoint tests.
    monkeypatch.setattr(
        main,
        "search_hybrid",
        lambda query_text, **kwargs: [
            {
                "job_id": 1,
                "faiss_id": 0,
                "title": "Data Scientist",
                "company": "ACME",
                "description": "",
                "qualifications": "",
                "responsibilities": "",
                "skills": "python",
                "experience": "junior",
                "location": "Cairo",
                "work_type": "remote",
                "salary_range": "",
                "similarity_score": 0.9,
            }
        ],
    )

    # Avoid Azure SQL resume lookup; keep it deterministic.
    def fake_resume_text(user_id):
        return "my resume"

    fake_resume_text.cache_clear = lambda: None
    monkeypatch.setattr(main, "get_resume_text_for_user", fake_resume_text)

    yield SyncASGIClient(main.app)


def test_health_ok(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "model_loaded" in body
    assert "index_loaded" in body


def test_clear_cache_ok(client):
    res = client.post("/clear-cache")
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
        json={
            "user_id": "user-1",
            "location": None,
            "work_type": None,
            "experience": None,
            "limit": 5,
        },
    )
    assert res.status_code == 200
    jobs = res.json()["jobs"]
    assert len(jobs) == 1
    assert set(jobs[0].keys()) == {
        "job_id",
        "title",
        "company",
        "location",
        "work_type",
        "experience",
        "salary_range",
        "similarity_score",
    }

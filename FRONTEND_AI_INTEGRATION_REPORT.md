# Jobify AI Backend Frontend Integration Report

## Current Services

- AI Backend local URL: `http://127.0.0.1:8000`
- Frontend local URL: `http://127.0.0.1:3000`
- Docker image: `omarfouda1234/jobify-ai-backend:latest`
- Docker artifact path: `/app/artifacts`
- Local test artifact paths:
  - `D:\Machine Learning Projects\ml\pro34\jobs.db`
  - `D:\Machine Learning Projects\ml\pro34\jobs.index`

## Required Frontend Environment

For Next.js server routes:

```env
AI_BACKEND_URL=http://127.0.0.1:8000
NEXT_PUBLIC_BACKEND_URL=<main-dotnet-backend-url>
```

For Docker or deployed AI backend, keep the `.env` file with:

```env
HF_REPO_ID=omaralifouda/jobify-artifacts
HF_REPO_TYPE=dataset
HF_DB_FILENAME=jobs.db
HF_INDEX_FILENAME=jobs.index
HF_ARTIFACT_DIR=/app/artifacts
DB_PATH=/app/artifacts/jobs.db
INDEX_PATH=/app/artifacts/jobs.index
JWT_SECRET=<strong-secret>
ADMIN_API_KEY=<strong-secret>
```

Do not commit `.env`. It contains secrets.

## Frontend API Routes Already Present

These Next.js routes proxy requests from the frontend UI to the AI backend:

| Frontend Route | AI Backend Endpoint | Purpose |
| --- | --- | --- |
| `POST /api/ai/search` | `/search` or `/recommend-matches` | Job semantic search and applicant recommendations |
| `POST /api/ai/chat` | `/chat` | Applicant career chatbot |
| `POST /api/ai/company/chat` | `/chat/company/message` | Company/recruiter chatbot |
| `POST /api/ai/company/find-candidates` | `/chat/company/find-candidates` | Rank applicants for a job |

## Direct AI Backend Endpoints

### Health

```http
GET /health
GET /health/app-db
```

Expected:

```json
{
  "status": "ok",
  "model_loaded": true,
  "index_loaded": true,
  "jobs_db_exists": true,
  "index_exists": true
}
```

### Search Jobs

```http
POST /search
Content-Type: application/json
```

```json
{
  "query": "machine learning python fastapi data science",
  "location": null,
  "work_type": null,
  "experience": null,
  "limit": 3
}
```

Returns:

```json
{
  "jobs": [
    {
      "job_id": 1585229071670743,
      "title": "Data Scientist",
      "company": "Intuit",
      "similarity_score": 0.6111,
      "embedding_source": "faiss_local"
    }
  ]
}
```

### Recommend Matches for Applicant

```http
POST /recommend-matches
Content-Type: application/json
```

```json
{
  "user_id": "d5ce65a3-599f-457a-8aef-cb2621f4146e",
  "location": null,
  "work_type": null,
  "experience": null,
  "limit": 3
}
```

This uses the applicant active resume from the connected SQL database.

### Analyze Local Indexed Job Against CV

```http
POST /analyze-job-id
Content-Type: application/json
```

```json
{
  "user_id": "d5ce65a3-599f-457a-8aef-cb2621f4146e",
  "job_id": 1585229071670743
}
```

### Applicant Chatbot

```http
POST /chat
Content-Type: application/json
```

```json
{
  "message": "Say one short CV improvement tip.",
  "user_id": "d5ce65a3-599f-457a-8aef-cb2621f4146e"
}
```

If the message asks for job recommendations, for example `"recommend jobs for me"` or `"رشحلي وظائف مناسبة"`, the backend now reuses the same recommendation search logic used by `POST /recommend-matches`.

Recommended response shape:

```json
{
  "reply": "The best matching roles for your CV are...",
  "recommended_jobs": [
    {
      "job_id": 1585229071670743,
      "title": "Data Scientist",
      "company": "Intuit",
      "location": "Remote",
      "work_type": "Remote",
      "experience": "Mid Level",
      "salary_range": "",
      "similarity_score": 0.6111
    }
  ]
}
```

Frontend usage:

- Use `POST /recommend-matches` directly for the `Recommended for You` page/section.
- Use `POST /chat` for chatbot messages. When `recommended_jobs` exists, render those jobs inside the chat message as clickable job cards.

### Company Chatbot

```http
POST /chat/company/message
Content-Type: application/json
```

```json
{
  "company_id": "AB16E3E4-B398-454E-B62B-0F2D6BAD9411",
  "job_posting_id": "DA16524B-3634-4429-A1F0-4B8527100B79",
  "message": "Give one short hiring insight for this job."
}
```

### Company Analysis

```http
POST /chat/company/analyze-company
Content-Type: application/json
```

```json
{
  "company_id": "AB16E3E4-B398-454E-B62B-0F2D6BAD9411"
}
```

### Job Post Analysis

```http
POST /chat/company/analyze-job-post
Content-Type: application/json
```

```json
{
  "company_id": "AB16E3E4-B398-454E-B62B-0F2D6BAD9411",
  "job_posting_id": "DA16524B-3634-4429-A1F0-4B8527100B79"
}
```

### Hiring Insights

```http
POST /chat/company/hiring-insights
Content-Type: application/json
```

```json
{
  "company_id": "AB16E3E4-B398-454E-B62B-0F2D6BAD9411",
  "job_posting_id": "DA16524B-3634-4429-A1F0-4B8527100B79"
}
```

### Generate Job Post Draft

```http
POST /chat/company/generate-job-post
Content-Type: application/json
```

```json
{
  "company_id": "AB16E3E4-B398-454E-B62B-0F2D6BAD9411",
  "role": "Junior Machine Learning Engineer",
  "skills": ["Python", "FastAPI", "SQL"],
  "work_type": "Full-Time",
  "location": "Cairo"
}
```

### Find Candidates

```http
POST /chat/company/find-candidates
Content-Type: application/json
```

```json
{
  "company_id": "F3780E06-781D-4733-B194-4F07F39C0F9C",
  "job_posting_id": "C06D4F7D-E8D4-4430-834B-7BF264E4EF56",
  "limit": 3
}
```

Returns candidate list with `match_score`.

### Sync Newly Created SQL Job Into FAISS/SQLite

After the main backend creates a new SQL Server job posting, call:

```http
POST /admin/sync-job-embedding
X-Admin-API-Key: <ADMIN_API_KEY>
Content-Type: application/json
```

```json
{
  "company_id": "AB16E3E4-B398-454E-B62B-0F2D6BAD9411",
  "job_posting_id": "DA16524B-3634-4429-A1F0-4B8527100B79"
}
```

Important: SQL Server `JobID` values can be GUID strings. The AI backend now supports GUID job ids for this sync endpoint.

### Sync Applicant Resume Embedding After CV Upload

After the main backend uploads or replaces an applicant CV and saves the active resume row, call:

```http
POST /admin/sync-resume-embedding
X-Admin-API-Key: <ADMIN_API_KEY>
Content-Type: application/json
```

```json
{
  "user_id": "d5ce65a3-599f-457a-8aef-cb2621f4146e",
  "force": true
}
```

The AI backend stores the CV vector in `dbo.ResumeEmbeddings` with:

`UserId`, `ApplicantID`, `ResumeID`, `ResumePath`, `ModelName`, `Dimension`, `TextHash`, `Embedding`, `CreatedAt`, `UpdatedAt`.

`POST /recommend-matches` and recommendation-aware `POST /chat` use this stored embedding first. If no row exists yet, the AI backend creates it automatically as a fallback.

### Cache Utilities

```http
POST /clear-cache
X-Admin-API-Key: <ADMIN_API_KEY>
```

```http
POST /admin/invalidate-resume-cache?user_id=<USER_ID>
X-Admin-API-Key: <ADMIN_API_KEY>
```

## Latest Real Test Results

The following were tested successfully against the connected SQL database and local artifacts:

- `GET /health`: `200`
- `GET /health/app-db`: `200`
- `POST /admin/sync-resume-embedding`: `200`
- `POST /search`: `200`
- `POST /recommend-matches`: `200`
- `POST /analyze-job-id`: `200`
- `POST /chat`: `200`
- `POST /chat/company/message`: `200`
- `POST /chat/company/analyze-company`: `200`
- `POST /chat/company/analyze-job-post`: `200`
- `POST /chat/company/hiring-insights`: `200`
- `POST /chat/company/generate-job-post`: `200`
- `POST /chat/company/find-candidates`: `200`
- `POST /admin/sync-job-embedding`: `200`
- `POST /clear-cache`: `200`
- `POST /admin/invalidate-resume-cache`: `200`
- Frontend `POST /api/ai/search`: `200`
- Frontend `POST /api/ai/chat`: `200`
- Frontend `POST /api/ai/company/chat`: `200`
- Frontend `POST /api/ai/company/find-candidates`: `200`

The test CV file `D:\desktop\omar_fouda_cv.pdf` was parsed successfully with about 4292 extracted characters.

## Notes for Frontend Developer

- Use the existing Next.js API routes instead of calling the AI backend directly from browser components.
- The routes automatically forward the auth token cookie when present.
- For local testing, keep `AI_BACKEND_URL=http://127.0.0.1:8000`.
- For Docker image handoff, use `omarfouda1234/jobify-ai-backend:latest`.
- The first Docker run downloads `jobs.db` and `jobs.index` from Hugging Face into the `hf-artifacts` Docker volume.
- If the Hugging Face dataset is private, `.env` must include `HF_TOKEN`.
- If multiple AI backend replicas are used later, `/admin/sync-job-embedding` updates only the container instance that receives the request. Use one AI backend instance for the graduation deployment, or move to a shared vector database later.

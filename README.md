# AI Job Backend - Hosted SQL Server Ready Version

This version is prepared for integration with the graduation project's hosted SQL Server backend, for example `SQL9001.site4now.net`.

## What this version includes

- FastAPI backend for job recommendation and analysis.
- Local FAISS + SQLite search over `job_descriptions.csv`.
- Hosted SQL Server integration through `pyodbc`.
- Active CV retrieval by `user_id` from the project database.
- PDF/DOCX CV text extraction.
- Gemini analysis and career chat.
- Dockerfile with Microsoft ODBC Driver 18 for SQL Server.
- `/health/app-db` endpoint to test SQL Server connection.
- `/admin/sync-job-embedding` endpoint to add new SQL Server jobs to `jobs.db` and `jobs.index`.
- Backend handoff documentation and SQL script.

## Important backend requirement

The main application database must support this query:

```sql
SELECT TOP 1 r.FilePath
FROM Applicant a
JOIN Resume r ON r.ApplicantID = a.ApplicantID
WHERE a.UserId = @UserId AND r.IsActive = 1
ORDER BY r.UploadDate DESC;
```

See:

- `docs/backend_handoff_detailed.docx`
- `docs/backend_handoff_detailed.md`
- `sql/backend_required_changes.sql`

## Before running

1. Copy `.env.example` to `.env`.
2. Fill SQL Server credentials.
3. Fill Hugging Face settings:
   - `HF_REPO_ID=omaralifouda/jobify-artifacts`
   - `HF_TOKEN=...` if the dataset repo is private.
4. Run the required SQL script on the hosted database:

```bash
sql/backend_required_changes.sql
```

5. Run ingestion:

```bash
python ingest.py
```

This step is only needed when regenerating local `jobs.db` and `jobs.index`. Docker downloads the current artifacts from Hugging Face automatically.

6. Start the API:

```bash
docker compose up --build
```

## Health checks

```bash
GET /health
GET /health/app-db
```

## API endpoints

- `GET /health`
- `GET /health/app-db`
- `POST /recommend-matches`
- `POST /analyze-job-id`
- `POST /search`
- `POST /chat`
- `POST /admin/sync-job-embedding`
- `POST /admin/sync-resume-embedding`
- `POST /clear-cache`

`POST /chat` is recommendation-aware. When the applicant sends a job-matching message such as `recommend jobs for me`, `find jobs that match my skills`, or `show me remote jobs` and includes `user_id`, the response includes `recommended_jobs` using the same hybrid search logic as `POST /recommend-matches`. Short greetings such as `hi` or `hello` return a lightweight greeting and do not inject CV context, so the chatbot does not unexpectedly analyze the resume. The frontend should render `recommended_jobs` inside the chatbot as job cards, while the `Recommended for You` section can continue calling `POST /recommend-matches` directly.

## Production note

`Resume.FilePath` should be an HTTP/HTTPS URL to a reachable PDF or DOCX file.
Local Windows paths like `C:\Users\...` will not work in Docker/cloud production.

`/search` and `/recommend-matches` use local `jobs.index` and `jobs.db` files. In Docker, the startup script downloads them from Hugging Face into `/app/artifacts` when they are missing.

## Live Job Embedding Sync

When the main backend creates a new job in the deployed SQL Server database, it should call the AI backend immediately after the SQL insert succeeds:

```http
POST /admin/sync-job-embedding
X-Admin-API-Key: <ADMIN_API_KEY>
Content-Type: application/json

{
  "job_posting_id": "123",
  "company_id": "45"
}
```

The AI backend will:

1. Read the job from SQL Server.
2. Build the searchable job text.
3. Create an embedding with the configured SentenceTransformer model.
4. Append the vector to `jobs.index`.
5. Insert or replace the job metadata in `jobs.db`.

If the same `JobID` is synced again, SQLite points that job to the newest vector. Older orphan vectors may remain in FAISS, but they are ignored because they no longer have a matching row in `jobs.db`.

## Live Resume Embedding Sync

When the main backend uploads or replaces an applicant CV, it should call the AI backend after the SQL resume record is saved:

```http
POST /admin/sync-resume-embedding
X-Admin-API-Key: <ADMIN_API_KEY>
Content-Type: application/json

{
  "user_id": "<APPLICANT_USER_ID>",
  "force": true
}
```

The AI backend will read the active resume from SQL Server, extract PDF/DOCX text, generate a normalized embedding, and store it in `dbo.ResumeEmbeddings`. `POST /recommend-matches` and recommendation-aware `POST /chat` use this stored CV embedding first, which avoids parsing and embedding the CV on every request.

`dbo.ResumeEmbeddings` columns:

- `UserId`
- `ApplicantID`
- `ResumeID`
- `ResumePath`
- `ModelName`
- `Dimension`
- `TextHash`
- `Embedding`
- `CreatedAt`
- `UpdatedAt`

If the stored embedding is missing, recommendations automatically create it as a fallback.

## Live Resume Cache Invalidation

If the main backend cannot call the resume sync endpoint, it can still invalidate the AI backend cache after a candidate uploads a new CV:

```http
POST /admin/invalidate-resume-cache?user_id=<USER_ID>
X-Admin-API-Key: <ADMIN_API_KEY>
```

The AI backend evicts the cached text representation and deletes the stored resume embedding for the given `user_id`, ensuring the next request pulls, parses, and re-embeds the updated file.


## Scaling & Replica Constraints

> [!WARNING]
> This service is designed to run as a **single replica (single instance)**.
> Because the FAISS index and local metadata are stored in files (`jobs.index` and `jobs.db`) local to the container instance, calls to `/admin/sync-job-embedding` only update the specific container instance receiving the request. Horizontally scaling to multiple replicas without a shared vector store / centralized DB (e.g. pgvector, Qdrant) or a pub/sub sync mechanism will lead to search result inconsistency between replicas.

## Docker Search Artifacts

This deployment keeps the image small and downloads the search artifacts at container startup:

- `jobs.db`
- `jobs.index`

Docker Compose stores them in the `hf-artifacts` volume mounted at `/app/artifacts`, so they are cached between restarts. Set `HF_REPO_ID` and `HF_TOKEN` in `.env` before running `docker compose up --build`.

## Do not commit

- `.env`
- `jobs.db`
- `jobs.index`
- `job_descriptions.csv` if it is large/private

## Company AI Chatbot Test Build

This version includes company dashboard chatbot endpoints for `/dashboard/company/ai-chat`.

### New endpoints
- `POST /chat/company/message`
- `POST /chat/company/analyze-company`
- `POST /chat/company/analyze-job-post`
- `POST /chat/company/hiring-insights`
- `POST /chat/company/generate-job-post`
- `POST /chat/company/find-candidates`

### Test UI
Open `index.html` and enter:
- `company_user_id` from logged-in company session, or
- `company_id` for local testing.

### Database changes
No new tables are required for company AI.
Run the optional indexes file:

```bash
sql/company_ai_optional_indexes.sql
```

Resume requirements from previous handoff still apply:
- `Resume.IsActive BIT DEFAULT 0`
- only one active resume per applicant
- `Resume.FilePath` should be a reachable PDF/DOCX URL in production

See:
- `docs/company_ai_backend_handoff.md`
- `docs/company_ai_backend_handoff.docx`

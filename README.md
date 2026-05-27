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
3. Put `job_descriptions.csv` in the project root.
4. Run the required SQL script on the hosted database:

```bash
sql/backend_required_changes.sql
```

5. Run ingestion:

```bash
python ingest.py
```

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
- `POST /clear-cache`

## Production note

`Resume.FilePath` should be an HTTP/HTTPS URL to a reachable PDF or DOCX file.
Local Windows paths like `C:\Users\...` will not work in Docker/cloud production.

`/search` and `/recommend-matches` use the bundled local `jobs.index` and `jobs.db` files. This is the Docker image deployment mode.

## Docker image search files

This deployment bundles the local search artifacts into the Docker image:

- `jobs.db`
- `jobs.index`

The container reads `/app/jobs.db` and `/app/jobs.index` directly from the image, so Docker Compose no longer needs to mount those files as volumes.
These files are intentionally not stored in Git because they are too large for normal GitHub pushes. Keep them in the project root before running `docker compose build`.

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

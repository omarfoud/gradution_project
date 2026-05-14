# Release Notes - Azure Ready Final Version

## Changed in this version

- Updated `.env.example` to use Azure SQL style values.
- Added `REQUIRE_REMOTE_RESUME_URL=true` to enforce URL-based CV paths in production.
- Added `/health/app-db` endpoint to test Azure SQL connectivity.
- Confirmed Dockerfile installs Microsoft ODBC Driver 18.
- Added backend handoff document in DOCX and Markdown.
- Added SQL script for required database changes.
- Kept FAISS + SQLite as local AI search storage.

## Files for backend team

- `docs/backend_handoff_detailed.docx`
- `docs/backend_handoff_detailed.md`
- `sql/backend_required_changes.sql`

## Main integration rule

Backend must make sure each Applicant has only one active Resume and that `Resume.FilePath` is reachable by the AI backend.

## v5.0.0 - Company AI Chatbot Test Build

Added company dashboard AI endpoints:
- `POST /chat/company/message`
- `POST /chat/company/analyze-company`
- `POST /chat/company/analyze-job-post`
- `POST /chat/company/hiring-insights`
- `POST /chat/company/generate-job-post`
- `POST /chat/company/find-candidates`

UI update:
- `index.html` is now a company AI testing dashboard matching the `/dashboard/company/ai-chat` flow.

Database:
- No new tables required.
- Added optional performance indexes in `sql/company_ai_optional_indexes.sql`.
- `Resume.IsActive` and reachable `Resume.FilePath` URL are still required.

Startup:
- API can start without `jobs.db` / `jobs.index` so company AI endpoints can be tested before local FAISS ingestion.
- Applicant matching endpoints still require `python ingest.py`.

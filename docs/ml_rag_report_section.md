# Machine Learning and RAG Module

## 1. Introduction

The AI module is responsible for improving the job matching experience in the recruitment system. It connects the main application database with a machine learning search layer and a generative AI layer. The module recommends suitable jobs for applicants, analyzes how well a CV matches a selected job, supports career chat, and provides company-side recruitment assistance.

The system uses a hybrid approach. Structured business data such as applicants, resumes, companies, job posts, and applications is stored in the main hosted SQL Server database, such as `SQL9001.site4now.net`. Large-scale job search is handled by a local SQLite database and a FAISS vector index. The generative layer uses Gemini to produce readable recommendations, explanations, hiring insights, and candidate rankings.

## 2. Module Objectives

- Recommend relevant jobs based on the applicant's active CV.
- Analyze the similarity between a candidate CV and a selected job.
- Allow general job search using semantic search and metadata filters.
- Support company recruiters with AI chat, job post analysis, job post generation, hiring insights, and candidate ranking.
- Integrate with the existing ERD without adding unnecessary tables to the main database.

## 3. ERD Integration Review

The AI backend is connected to the current ERD through the existing recruitment entities. No new main database tables are required for the ML and RAG features.

| ERD Entity | Used By AI Module | Integration Purpose |
| --- | --- | --- |
| `ApplicationUser` | Applicant and company context | The frontend sends `ApplicationUser.Id` as `user_id` or `company_user_id`. |
| `Applicant` | Applicant recommendation and candidate ranking | Links the logged-in user to applicant profile data through `Applicant.UserId`. |
| `Resume` | CV retrieval and CV text extraction | Stores uploaded CV file data. The AI module reads the active resume using `ApplicantID` and `IsActive`. |
| `Company` | Company AI chatbot | Resolves the logged-in company using `Company.UserId`. |
| `JobPosting` | Company job post analysis and candidate ranking | Ensures the requested job belongs to the logged-in company. |
| `Application` | Candidate ranking and hiring KPIs | Connects applicants to job postings and provides application status and applied date. |
| `JobMetric` | Existing ERD analytics support | Can be used later to enrich hiring insights with views and application counts. |

The required resume lookup query is:

```sql
SELECT TOP 1 r.FilePath
FROM Applicant a
JOIN Resume r ON r.ApplicantID = a.ApplicantID
WHERE a.UserId = @UserId AND r.IsActive = 1
ORDER BY r.UploadDate DESC;
```

The ERD shows singular table/entity names such as `Applicant`, `Resume`, `Company`, `JobPosting`, and `Application`. The implementation was reviewed and updated to use the same singular names in SQL Server queries, so the AI service now matches the database model shown in the ERD.

## 4. Software Requirements

- Python 3.9 or later.
- FastAPI for API endpoints.
- Uvicorn for running the API server.
- Pandas and NumPy for data preprocessing.
- Sentence Transformers for generating text embeddings.
- FAISS for vector similarity search.
- SQLite for local job metadata storage.
- PyODBC and Microsoft ODBC Driver 18 for SQL Server connection.
- PyPDF2 and python-docx for CV text extraction.
- Google Generative AI SDK for Gemini responses.
- Docker and Docker Compose for deployment.

## 5. Data Sources

The module uses three main data sources:

1. `job_descriptions.csv`: the raw job dataset used to build the semantic search index.
2. `jobs.db`: a generated SQLite database containing structured job metadata.
3. `jobs.index`: a generated FAISS index containing job embeddings for fast similarity search.

The main application database remains the source of truth for applicants, resumes, companies, job posts, and applications.

## 6. Machine Learning Pipeline

### 6.1 Data Ingestion

The ingestion script reads the job dataset in chunks to support large files. For each job, it combines important textual fields into one searchable text representation:

- Job title
- Skills
- Qualifications
- Responsibilities
- Job description
- Experience level
- Location
- Work type

The combined text is encoded using the `all-MiniLM-L6-v2` Sentence Transformer model. The embeddings are normalized and stored in FAISS using an IVF Flat index with inner product similarity. At the same time, the job metadata is stored in SQLite with a `faiss_id` that links each database row to its vector.

### 6.2 Semantic Search

When a user searches or requests recommendations, the input text is converted into an embedding using the same Sentence Transformer model. FAISS retrieves the nearest job vectors, then SQLite returns the full job details. Optional filters such as location, work type, and experience are applied at the metadata level.

### 6.3 Job Recommendation

For applicant recommendations, the backend first retrieves the applicant's active CV from the main database. The CV file is downloaded or read, then text is extracted from PDF or DOCX format. This CV text becomes the semantic query used to retrieve the most relevant jobs from FAISS and SQLite.

The endpoint returns concise job summaries including job id, title, company, location, work type, experience, salary range, and similarity score.

## 7. RAG Architecture

The system follows a Retrieval-Augmented Generation pattern. It does not ask the language model to answer from memory only. Instead, it retrieves relevant application data first, then sends that retrieved context to Gemini.

### 7.1 Retrieval

The retrieval layer collects context from different sources depending on the feature:

- Applicant active CV from `Applicant` and `Resume`.
- Job metadata from SQLite and FAISS.
- Company profile from `Company`.
- Job post ownership and details from `JobPosting`.
- Applications and candidate data from `Application`, `Applicant`, and `Resume`.
- Hiring KPIs from application counts and status breakdowns.

### 7.2 Augmentation

The backend builds structured prompts that include only the relevant retrieved data. For example, job analysis prompts include the candidate CV, job title, company, skills, qualifications, responsibilities, work type, salary range, and job description. Candidate ranking prompts include the company, job post, applicant data, and resume previews.

### 7.3 Generation

Gemini generates the final response in a structured format. The model is used for explanation and decision support, while the actual facts come from the retrieved database and vector search context.

The generated outputs include:

- Match percentage and explanation.
- Candidate strengths and missing skills.
- Short improvement plan.
- Job post quality score.
- Hiring risks and recruiter actions.
- Ranked candidates with strengths, gaps, and recommendations.

## 8. Main API Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Checks model, FAISS index, SQLite files, SQL configuration, and Gemini configuration. |
| `GET /health/app-db` | Tests the hosted SQL Server database connection. |
| `POST /recommend-matches` | Recommends jobs using the applicant's active CV. |
| `POST /analyze-job-id` | Analyzes one job against the applicant's CV using RAG. |
| `POST /search` | Performs semantic job search using a text query. |
| `POST /chat` | Provides general career guidance using Gemini. |
| `POST /chat/company/message` | Provides company dashboard AI chat. |
| `POST /chat/company/analyze-company` | Analyzes the company profile for hiring attractiveness. |
| `POST /chat/company/analyze-job-post` | Reviews and improves a specific job posting. |
| `POST /chat/company/hiring-insights` | Generates insights from hiring KPIs. |
| `POST /chat/company/generate-job-post` | Creates a job post draft from recruiter inputs. |
| `POST /chat/company/find-candidates` | Ranks applicants for a selected job post. |

## 9. Database Requirements

The main database must include `Resume.IsActive` so the AI backend can select the latest active CV for each applicant.

```sql
ALTER TABLE Resume ADD IsActive BIT DEFAULT 0;
```

Only one resume should be active for each applicant. When a new CV is uploaded, old resumes should be deactivated inside a transaction.

```sql
BEGIN TRANSACTION;

UPDATE Resume
SET IsActive = 0
WHERE ApplicantID = @ApplicantID;

INSERT INTO Resume (FileName, FilePath, UploadDate, IsActive, ApplicantID)
VALUES (@FileName, @FilePath, GETDATE(), 1, @ApplicantID);

COMMIT TRANSACTION;
```

Recommended indexes:

```sql
CREATE INDEX IX_Resume_ApplicantID_IsActive_UploadDate
ON Resume(ApplicantID, IsActive, UploadDate DESC);

CREATE INDEX IX_Company_UserId
ON Company(UserId);

CREATE INDEX IX_JobPosting_CompanyID_JobID
ON JobPosting(CompanyID, JobID);

CREATE INDEX IX_Application_JobPostingID_AppliedDate
ON Application(JobPostingID, AppliedDate DESC);
```

## 10. Deployment Notes

The module can run locally or inside Docker. In production, CV file paths should be reachable URLs. Local Windows file paths are not suitable for Docker or hosted deployment because the AI container cannot access files stored on another machine.

Important environment variables include:

```env
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
SQL_SERVER=SQL9001.site4now.net
SQL_DATABASE=
SQL_USERNAME=
SQL_PASSWORD=
SQL_DRIVER=ODBC Driver 18 for SQL Server
CSV_PATH=job_descriptions.csv
DB_PATH=jobs.db
INDEX_PATH=jobs.index
MODEL_NAME=all-MiniLM-L6-v2
```

## 11. Testing and Validation

The project includes automated tests for API behavior, resume file handling, and ERD table-name alignment. The current test suite passes successfully.

Validation checklist:

- `GET /health` returns status `ok`.
- `GET /health/app-db` connects to the hosted SQL Server.
- `Resume.IsActive` exists in the database.
- `Resume.FilePath` stores reachable PDF or DOCX URLs.
- `python ingest.py` creates `jobs.db` and `jobs.index`.
- `/recommend-matches` returns ranked jobs for a real applicant user id.
- `/analyze-job-id` returns a structured CV-job match analysis.
- Company endpoints only access jobs that belong to the logged-in company.

## 12. Limitations and Future Work

- The FAISS and SQLite job store is generated from a CSV file, so updates require re-running ingestion.
- The current vector store is local. A future production version could use PostgreSQL with pgvector, Qdrant, Pinecone, Weaviate, or another managed vector search service.
- Candidate ranking depends on the quality and availability of resume files.
- The AI output should support recruiter decisions, but final hiring decisions should remain human-reviewed.
- Additional ERD entities such as `Skill`, `ApplicantSkill`, `Experience`, `SavedJobs`, and `JobMetric` can later enrich recommendations and analytics.

## 13. Conclusion

The ML and RAG module adds intelligent job matching and recruitment assistance to the existing system while staying aligned with the current ERD. The module uses the hosted SQL Server database for trusted application data, FAISS and SQLite for fast semantic retrieval, and Gemini for structured natural language analysis. This design keeps the database model clean, improves applicant recommendations, and gives companies practical AI support during the hiring process.

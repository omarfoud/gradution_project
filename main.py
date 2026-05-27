import concurrent.futures
import io
import logging
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Optional

import docx
import faiss
import google.generativeai as genai
import jwt
import pyodbc
import PyPDF2
import requests
from cachetools.func import ttl_cache
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("job-assistant")

# -----------------------------
# Configuration
# -----------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MODEL_NAME = os.getenv("MODEL_NAME", "all-MiniLM-L6-v2")
DEVICE = os.getenv("DEVICE", "cpu")

DB_PATH = os.getenv("DB_PATH", "jobs.db")
INDEX_PATH = os.getenv("INDEX_PATH", "jobs.index")

SQL_SERVER = os.getenv("SQL_SERVER")
SQL_PORT = os.getenv("SQL_PORT", "1433")
SQL_DATABASE = os.getenv("SQL_DATABASE")
SQL_USERNAME = os.getenv("SQL_USERNAME")
SQL_PASSWORD = os.getenv("SQL_PASSWORD")
SQL_DRIVER = os.getenv("SQL_DRIVER", "ODBC Driver 18 for SQL Server")
SQL_ENCRYPT = os.getenv("SQL_ENCRYPT", "yes")


JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() in ("true", "1", "yes")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")


def get_sql_identifier(env_name: str, default: str) -> str:
    value = os.getenv(env_name, default).strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise RuntimeError(f"Invalid SQL identifier in {env_name}: {value}")
    return value


APPLICANT_TABLE = get_sql_identifier("SQL_TABLE_APPLICANT", "Applicants")
RESUME_TABLE = get_sql_identifier("SQL_TABLE_RESUME", "Resumes")
COMPANY_TABLE = get_sql_identifier("SQL_TABLE_COMPANY", "Companies")
JOB_POSTING_TABLE = get_sql_identifier("SQL_TABLE_JOB_POSTING", "JobPostings")
APPLICATION_TABLE = get_sql_identifier("SQL_TABLE_APPLICATION", "Applications")

ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",") if origin.strip()]

FAISS_TOP_K = int(os.getenv("FAISS_TOP_K", "500"))
RESULTS_LIMIT = int(os.getenv("RESULTS_LIMIT", "10"))
MAX_CV_CHARS = int(os.getenv("MAX_CV_CHARS", "4000"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
SQL_BATCH_SIZE = int(os.getenv("SQL_BATCH_SIZE", "900"))
REQUIRE_REMOTE_RESUME_URL = os.getenv("REQUIRE_REMOTE_RESUME_URL", "true").lower() in {"1", "true", "yes", "y"}

MODEL: Optional[SentenceTransformer] = None
INDEX = None

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY is not configured. /chat and /analyze-job-id will fail until it is set.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global MODEL, INDEX

    try:
        logger.info("Loading embedding model: %s on %s", MODEL_NAME, DEVICE)
        MODEL = SentenceTransformer(MODEL_NAME, device=DEVICE)
    except Exception as exc:
        logger.error("FAILED to load embedding model '%s': %s", MODEL_NAME, exc, exc_info=True)
        MODEL = None

    # Use os.path.isfile to avoid empty directories created by Docker volumes.
    if not os.path.isfile(DB_PATH) or not os.path.isfile(INDEX_PATH):
        logger.warning(
            "jobs.db or jobs.index not found (or are empty directories created by Docker volumes). "
            "Local FAISS search will be skipped until you run: python ingest.py"
        )
    else:
        try:
            logger.info("Loading FAISS index: %s", INDEX_PATH)
            INDEX = faiss.read_index(INDEX_PATH)
            if hasattr(INDEX, "nprobe"):
                INDEX.nprobe = int(os.getenv("FAISS_NPROBE", "20"))
        except Exception as exc:
            logger.error("FAILED to load FAISS index '%s': %s", INDEX_PATH, exc, exc_info=True)
            INDEX = None

    logger.info("Backend is ready")
    yield


app = FastAPI(title="Job Assistant API", version="4.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Request models
# -----------------------------
class RecommendRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    location: Optional[str] = None
    work_type: Optional[str] = None
    experience: Optional[str] = None
    limit: int = Field(default=5, ge=1, le=50)


class AnalyzeJobRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    job_id: int


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    location: Optional[str] = None
    work_type: Optional[str] = None
    experience: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=50)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    user_id: Optional[str] = None


def check_auth(requested_id: Optional[str], auth_header: Optional[str] = Header(None)) -> Optional[dict]:
    if not auth_header:
        if REQUIRE_AUTH:
            raise HTTPException(status_code=401, detail="Authorization header is required")
        return None

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header format. Use 'Bearer <token>'")
    
    token = parts[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}") from exc

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token is missing 'sub' claim")

    if requested_id and str(sub) != str(requested_id):
        raise HTTPException(status_code=403, detail="Forbidden: Token subject does not match requested context")
    
    return payload


class CompanyContextRequest(BaseModel):
    # Send company_user_id after company login. It should be ApplicationUser.Id from the frontend auth/session.
    # company_id can be used for local tests if the frontend does not have the user id yet.
    company_user_id: Optional[str] = None
    company_id: Optional[str] = None


class CompanyChatRequest(CompanyContextRequest):
    message: str = Field(..., min_length=1)
    job_posting_id: Optional[str] = None


class CompanyJobPostRequest(CompanyContextRequest):
    job_posting_id: str


class CompanyFindCandidatesRequest(CompanyContextRequest):
    job_posting_id: str
    limit: int = Field(default=10, ge=1, le=25)


class CompanyGenerateJobPostRequest(CompanyContextRequest):
    role: str = Field(..., min_length=1)
    level: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    work_type: Optional[str] = None
    location: Optional[str] = None
    salary_range: Optional[str] = None


class CompanyHiringInsightsRequest(CompanyContextRequest):
    job_posting_id: Optional[str] = None


# -----------------------------
# DB helpers
# -----------------------------
def get_jobs_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_app_db():
    missing = [
        name
        for name, value in {
            "SQL_SERVER": SQL_SERVER,
            "SQL_DATABASE": SQL_DATABASE,
            "SQL_USERNAME": SQL_USERNAME,
            "SQL_PASSWORD": SQL_PASSWORD,
        }.items()
        if not value
    ]
    if missing:
        raise HTTPException(status_code=500, detail=f"Missing SQL Server environment variables: {', '.join(missing)}")

    conn_str = (
        f"DRIVER={{{SQL_DRIVER}}};"
        f"SERVER={SQL_SERVER},{SQL_PORT};"
        f"DATABASE={SQL_DATABASE};"
        f"UID={SQL_USERNAME};"
        f"PWD={SQL_PASSWORD};"
        f"Encrypt={SQL_ENCRYPT};"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=10)


# -----------------------------
# Resume helpers
# -----------------------------
def get_resume_path_by_user_id(user_id: str) -> str:
    conn = get_app_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP 1 r.FilePath
            FROM {APPLICANT_TABLE} a
            JOIN {RESUME_TABLE} r ON r.ApplicantID = a.ApplicantID
            WHERE a.UserId = ? AND r.IsActive = 1
            ORDER BY r.UploadDate DESC
            """,
            user_id,
        )
        row = cursor.fetchone()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"SQL Server query failed: {exc}") from exc
    finally:
        conn.close()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Active resume not found for this user")
    return str(row[0])


def load_resume_bytes(resume_path: str) -> bytes:
    if resume_path.startswith(("http://", "https://")):
        try:
            response = requests.get(resume_path, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.content
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"Failed to download resume: {exc}") from exc

    if REQUIRE_REMOTE_RESUME_URL:
        raise HTTPException(
            status_code=400,
            detail="Resume.FilePath must be an http/https URL in production. Use a reachable file URL or set REQUIRE_REMOTE_RESUME_URL=false for local testing.",
        )

    if not os.path.exists(resume_path):
        raise HTTPException(status_code=404, detail=f"Resume file not found: {resume_path}")

    try:
        with open(resume_path, "rb") as file_obj:
            return file_obj.read()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read local resume file: {exc}") from exc


def extract_text(file_content: bytes, filename: str) -> str:
    lower_name = filename.lower().split("?")[0]
    is_pdf = lower_name.endswith(".pdf") or file_content.startswith(b"%PDF")
    is_docx = lower_name.endswith(".docx") or file_content.startswith(b"PK\x03\x04")
    is_html = file_content.startswith(b"<") or b"html" in file_content[:200].lower()

    try:
        if is_pdf:
            reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        elif is_docx:
            document = docx.Document(io.BytesIO(file_content))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        elif is_html:
            raise HTTPException(
                status_code=502,
                detail="Resume URL returned HTML, not a PDF/DOCX (possibly due to an authorization wall, redirect, or 404 error)"
            )
        else:
            raise HTTPException(status_code=400, detail="Only PDF and DOCX resumes are supported (extension not recognized or invalid file signature)")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read resume file: {exc}") from exc

    cleaned_text = text.strip()
    if not cleaned_text:
        raise HTTPException(status_code=400, detail="Resume text extraction returned empty content")
    return cleaned_text[:MAX_CV_CHARS]


@ttl_cache(maxsize=256, ttl=600)
def get_resume_text_for_user(user_id: str) -> str:
    resume_path = get_resume_path_by_user_id(user_id)
    file_content = load_resume_bytes(resume_path)
    return extract_text(file_content, resume_path)


# -----------------------------
# Job search helpers
# -----------------------------
@lru_cache(maxsize=512)
def encode_query_cached(query_text: str):
    if MODEL is None:
        raise HTTPException(status_code=503, detail="Embedding model is not loaded yet")
    vector = MODEL.encode([query_text], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(vector)
    return vector.copy()


def fetch_jobs_by_faiss_ids(conn: sqlite3.Connection, faiss_ids: list[int], filters: dict) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    for start in range(0, len(faiss_ids), SQL_BATCH_SIZE):
        batch = faiss_ids[start : start + SQL_BATCH_SIZE]
        placeholders = ",".join(["?"] * len(batch))
        query = f"SELECT * FROM jobs WHERE faiss_id IN ({placeholders})"
        params: list = list(batch)

        conditions = []
        if filters.get("location"):
            conditions.append("location LIKE ?")
            params.append(f"%{filters['location']}%")
        if filters.get("work_type"):
            conditions.append("work_type LIKE ?")
            params.append(f"%{filters['work_type']}%")
        if filters.get("experience"):
            conditions.append("experience LIKE ?")
            params.append(f"%{filters['experience']}%")

        if conditions:
            query += " AND " + " AND ".join(conditions)
        rows.extend(conn.execute(query, params).fetchall())
    return rows


def search_hybrid(query_text: str, *, k: int = RESULTS_LIMIT, location: Optional[str] = None, work_type: Optional[str] = None, experience: Optional[str] = None):
    if MODEL is None or INDEX is None:
        raise HTTPException(status_code=503, detail="FAISS search is not loaded yet. Run python ingest.py to create jobs.db and jobs.index.")
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=503, detail="jobs.db is missing. Run python ingest.py.")

    vector = encode_query_cached(query_text.strip())
    distances, indices = INDEX.search(vector, FAISS_TOP_K)

    valid_ids = [int(idx) for idx in indices[0] if idx != -1]
    if not valid_ids:
        return []

    # Keep similarity score to return a useful ranking signal.
    score_by_id = {int(idx): float(score) for idx, score in zip(indices[0], distances[0]) if idx != -1}
    id_to_rank = {idx: rank for rank, idx in enumerate(valid_ids)}

    conn = get_jobs_db()
    try:
        rows = fetch_jobs_by_faiss_ids(conn, valid_ids, {"location": location, "work_type": work_type, "experience": experience})
    finally:
        conn.close()

    sorted_rows = sorted(rows, key=lambda r: id_to_rank.get(r["faiss_id"], 10**9))

    results = []
    seen = set()
    for row in sorted_rows:
        job_id = row["job_id"]
        if job_id in seen:
            continue
        item = dict(row)
        item["similarity_score"] = round(score_by_id.get(row["faiss_id"], 0.0), 4)
        item["embedding_source"] = "faiss_local"
        results.append(item)
        seen.add(job_id)
        if len(results) >= k:
            break
    return results


# -----------------------------
# Prompt helpers
# -----------------------------
def build_analysis_prompt(job_row: sqlite3.Row, resume_text: str) -> str:
    return f"""
You are an expert career-matching assistant.
Compare the candidate CV against the job and be direct, practical, and fair.

Job:
- Title: {job_row['title']}
- Company: {job_row['company']}
- Experience: {job_row['experience']}
- Work Type: {job_row['work_type']}
- Salary Range: {job_row['salary_range']}
- Qualifications: {job_row['qualifications']}
- Responsibilities: {job_row['responsibilities']}
- Skills: {job_row['skills']}
- Description: {(job_row['description'] or '')[:1500]}

Candidate CV:
{resume_text[:2200]}

Return a clear structured answer with:
1. Match percentage
2. Why this percentage
3. Strengths
4. Missing skills / gaps
5. Short improvement plan
""".strip()


def generate_text(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured")
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        return response.text or "No response generated."
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc



# -----------------------------
# Company AI helpers
# -----------------------------
def ensure_company_context(company_user_id: Optional[str], company_id: Optional[str]) -> dict:
    if not company_user_id and company_id is None:
        raise HTTPException(status_code=400, detail="Send company_user_id from logged-in company session or company_id for local testing")

    conn = get_app_db()
    try:
        cursor = conn.cursor()
        if company_id is not None:
            cursor.execute(
                f"""
                SELECT TOP 1 CompanyID, Name, Industry, WebsiteURL, HeadquarterAddress, Location, LogoUrl, UserId
                FROM {COMPANY_TABLE}
                WHERE CompanyID = ?
                """,
                str(company_id),
            )
        else:
            cursor.execute(
                f"""
                SELECT TOP 1 CompanyID, Name, Industry, WebsiteURL, HeadquarterAddress, Location, LogoUrl, UserId
                FROM {COMPANY_TABLE}
                WHERE UserId = ?
                """,
                company_user_id,
            )
        row = cursor.fetchone()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Company lookup failed: {exc}") from exc
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Company not found for this logged-in user")

    return {
        "company_id": str(row[0]),
        "name": row[1],
        "industry": row[2],
        "website_url": row[3],
        "headquarter_address": row[4],
        "location": row[5],
        "logo_url": row[6],
        "user_id": row[7],
    }


def get_company_job_posting(company_id: str, job_posting_id: str) -> dict:
    conn = get_app_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP 1 JobID, Title, Description, Responsibility, MinSalary, MaxSalary, PostedDate, IsActive, IsRemote, CompanyID, JobTypes
            FROM {JOB_POSTING_TABLE}
            WHERE JobID = ? AND CompanyID = ?
            """,
            str(job_posting_id),
            str(company_id),
        )
        row = cursor.fetchone()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Job posting lookup failed: {exc}") from exc
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Job posting not found for this company")

    salary_range = "Negotiable"
    if row[4] is not None and row[5] is not None:
        salary_range = f"{float(row[4]):.2f} - {float(row[5]):.2f}"
    elif row[4] is not None:
        salary_range = f"{float(row[4]):.2f}+"
    elif row[5] is not None:
        salary_range = f"Up to {float(row[5]):.2f}"

    return {
        "job_id": str(row[0]),
        "title": row[1],
        "description": row[2],
        "responsibilities": row[3],
        "salary_range": salary_range,
        "posted_date": str(row[6]) if row[6] else None,
        "is_active": bool(row[7]),
        "is_remote": bool(row[8]),
        "company_id": str(row[9]),
        "job_type": str(row[10]) if row[10] is not None else None,
    }


def get_company_summary_for_prompt(company: dict) -> str:
    return f"""
Company:
- ID: {company['company_id']}
- Name: {company['name']}
- Industry: {company['industry']}
- Website: {company['website_url']}
- HQ: {company['headquarter_address']}
- Location: {company['location']}
""".strip()


def get_company_kpis(company_id: str, job_posting_id: Optional[str] = None) -> dict:
    conn = get_app_db()
    try:
        cursor = conn.cursor()
        if job_posting_id:
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM {APPLICATION_TABLE} a
                JOIN {JOB_POSTING_TABLE} jp ON jp.JobID = a.JobPostingID
                WHERE jp.CompanyID = ? AND jp.JobID = ?
                """,
                str(company_id),
                str(job_posting_id),
            )
            applications_count = int(cursor.fetchone()[0])

            cursor.execute(
                f"""
                SELECT TOP 10 CAST(a.ApplicationStatus AS NVARCHAR(100)) AS StatusName, COUNT(*) AS Total
                FROM {APPLICATION_TABLE} a
                JOIN {JOB_POSTING_TABLE} jp ON jp.JobID = a.JobPostingID
                WHERE jp.CompanyID = ? AND jp.JobID = ?
                GROUP BY CAST(a.ApplicationStatus AS NVARCHAR(100))
                ORDER BY Total DESC
                """,
                str(company_id),
                str(job_posting_id),
            )
        else:
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM {APPLICATION_TABLE} a
                JOIN {JOB_POSTING_TABLE} jp ON jp.JobID = a.JobPostingID
                WHERE jp.CompanyID = ?
                """,
                str(company_id),
            )
            applications_count = int(cursor.fetchone()[0])

            cursor.execute(
                f"""
                SELECT TOP 10 CAST(a.ApplicationStatus AS NVARCHAR(100)) AS StatusName, COUNT(*) AS Total
                FROM {APPLICATION_TABLE} a
                JOIN {JOB_POSTING_TABLE} jp ON jp.JobID = a.JobPostingID
                WHERE jp.CompanyID = ?
                GROUP BY CAST(a.ApplicationStatus AS NVARCHAR(100))
                ORDER BY Total DESC
                """,
                str(company_id),
            )
        status_breakdown = [{"status": str(r[0]), "count": int(r[1])} for r in cursor.fetchall()]

        cursor.execute(
            f"""
            SELECT TOP 10 jp.JobID, jp.Title, COUNT(a.ApplicationID) AS ApplicationCount
            FROM {JOB_POSTING_TABLE} jp
            LEFT JOIN {APPLICATION_TABLE} a ON a.JobPostingID = jp.JobID
            WHERE jp.CompanyID = ?
            GROUP BY jp.JobID, jp.Title
            ORDER BY ApplicationCount DESC
            """,
            str(company_id),
        )
        top_jobs = [{"job_id": str(r[0]), "title": r[1], "application_count": int(r[2])} for r in cursor.fetchall()]
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Company KPI query failed: {exc}") from exc
    finally:
        conn.close()

    return {"applications_count": applications_count, "status_breakdown": status_breakdown, "top_jobs": top_jobs}


def get_candidates_for_job(company_id: str, job_posting_id: str, limit: int) -> list[dict]:
    # Keep TOP value controlled by Pydantic limit to avoid SQL injection.
    limit = max(1, min(int(limit), 25))
    conn = get_app_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP (?)
                app.ApplicationID,
                applicant.ApplicantID,
                applicant.FirstName,
                applicant.LastName,
                applicant.Location,
                app.ApplicationStatus,
                app.AppliedDate,
                COALESCE(submittedResume.FilePath, activeResume.FilePath) AS ResumePath
            FROM {APPLICATION_TABLE} app
            JOIN {JOB_POSTING_TABLE} jp ON jp.JobID = app.JobPostingID
            JOIN {APPLICANT_TABLE} applicant ON applicant.ApplicantID = app.ApplicantID
            LEFT JOIN {RESUME_TABLE} submittedResume ON submittedResume.ResumeID = app.ResumeID
            LEFT JOIN {RESUME_TABLE} activeResume ON activeResume.ApplicantID = applicant.ApplicantID AND activeResume.IsActive = 1
            WHERE jp.CompanyID = ? AND jp.JobID = ?
            ORDER BY app.AppliedDate DESC
            """,
            limit,
            str(company_id),
            str(job_posting_id),
        )
        rows = cursor.fetchall()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Candidates query failed: {exc}") from exc
    finally:
        conn.close()

    return [
        {
            "application_id": r[0],
            "applicant_id": r[1],
            "name": f"{r[2] or ''} {r[3] or ''}".strip(),
            "location": r[4],
            "application_status": str(r[5]) if r[5] is not None else None,
            "applied_date": str(r[6]) if r[6] else None,
            "resume_path": r[7],
        }
        for r in rows
    ]


def build_company_chat_prompt(company: dict, message: str, job: Optional[dict] = None, kpis: Optional[dict] = None) -> str:
    job_part = f"\nRelated job posting:\n{job}" if job else ""
    kpi_part = f"\nCompany KPIs:\n{kpis}" if kpis else ""
    return f"""
You are an AI hiring assistant for a company dashboard.
Help recruiters improve job posts, attract better candidates, understand hiring metrics, and shortlist applicants.
Be concise, practical, and structured.

{get_company_summary_for_prompt(company)}
{job_part}
{kpi_part}

Recruiter question:
{message}
""".strip()


def build_job_post_analysis_prompt(company: dict, job: dict) -> str:
    return f"""
You are an expert recruitment copywriter and hiring analyst.
Analyze this job post for the company and return a clear structured answer.

{get_company_summary_for_prompt(company)}

Job posting:
{job}

Return:
1. Overall quality score out of 100
2. Clarity problems
3. Missing sections
4. Bias or vague wording risks
5. Improved qualifications section
6. Improved job description
7. Short action list for the recruiter
""".strip()


def build_candidates_prompt(company: dict, job: dict, candidates: list[dict]) -> str:
    def fetch_resume_preview(c: dict) -> dict:
        resume_preview = ""
        path = c.get("resume_path")
        if path:
            try:
                resume_preview = extract_text(load_resume_bytes(str(path)), str(path))[:1200]
            except Exception as exc:
                resume_preview = f"Could not read resume: {exc}"
        return {**c, "resume_preview": resume_preview}

    max_workers = min(len(candidates), 10) if candidates else 1
    safe_candidates = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_resume_preview, c) for c in candidates]
        concurrent.futures.wait(futures, timeout=15.0)
        
        for future, c in zip(futures, candidates):
            if future.done():
                try:
                    safe_candidates.append(future.result())
                except Exception as exc:
                    safe_candidates.append({**c, "resume_preview": f"Failed to fetch resume: {exc}"})
            else:
                safe_candidates.append({**c, "resume_preview": "Failed to fetch resume: Request timed out"})

    return f"""
You are an AI recruiter assistant.
Rank the applicants for this job based on the job responsibilities and resume previews.

{get_company_summary_for_prompt(company)}

Job posting:
{job}

Applicants:
{safe_candidates}

Return a JSON-like structured answer with:
- ranked_candidates: applicant_id, name, match_score out of 100, strengths, gaps, recommendation
- overall_notes
Do not invent information that is not supported by the applicant data.
""".strip()

# -----------------------------
# Endpoints
# -----------------------------
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "model_loaded": MODEL is not None,
        "index_loaded": INDEX is not None,
        "jobs_db_exists": os.path.exists(DB_PATH),
        "index_exists": os.path.exists(INDEX_PATH),
        "sql_server_configured": all([SQL_SERVER, SQL_DATABASE, SQL_USERNAME, SQL_PASSWORD]),
        "gemini_configured": bool(GEMINI_API_KEY),
        "require_remote_resume_url": REQUIRE_REMOTE_RESUME_URL,
    }


@app.get("/health/app-db")
def app_db_health_check():
    conn = get_app_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        value = cursor.fetchone()[0]
        return {"status": "ok", "sql_server_connection": bool(value)}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"SQL Server connection failed: {exc}") from exc
    finally:
        conn.close()


@app.post("/recommend-matches")
def recommend_matches(req: RecommendRequest, authorization: Optional[str] = Header(None)):
    check_auth(req.user_id, authorization)
    logger.info("Recommendation request user_id=%s limit=%s", req.user_id, req.limit)
    resume_text = get_resume_text_for_user(req.user_id)
    jobs = search_hybrid(resume_text, k=req.limit, location=req.location, work_type=req.work_type, experience=req.experience)
    return {"jobs": [{"job_id": j["job_id"], "title": j["title"], "company": j["company"], "location": j["location"], "work_type": j["work_type"], "experience": j["experience"], "salary_range": j["salary_range"], "similarity_score": j["similarity_score"]} for j in jobs]}


@app.post("/analyze-job-id")
def analyze_job_id(req: AnalyzeJobRequest, authorization: Optional[str] = Header(None)):
    check_auth(req.user_id, authorization)
    logger.info("Analysis request user_id=%s job_id=%s", req.user_id, req.job_id)
    resume_text = get_resume_text_for_user(req.user_id)
    conn = get_jobs_db()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (req.job_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job ID not found")
    return {"analysis": generate_text(build_analysis_prompt(row, resume_text))}


@app.post("/search")
def search_jobs(req: SearchRequest, authorization: Optional[str] = Header(None)):
    check_auth(None, authorization)
    logger.info("Search request query=%s limit=%s", req.query, req.limit)
    jobs = search_hybrid(req.query, k=req.limit, location=req.location, work_type=req.work_type, experience=req.experience)
    return {"jobs": jobs}


@app.post("/chat")
def chat_general(req: ChatRequest, authorization: Optional[str] = Header(None)):
    resume_context = ""
    if req.user_id:
        check_auth(req.user_id, authorization)
        try:
            resume_text = get_resume_text_for_user(req.user_id)
            resume_context = f"\nCandidate CV context:\n{resume_text[:2200]}\n"
        except Exception as exc:
            logger.warning("Could not load resume for user_id=%s in general chat: %s", req.user_id, exc)

    system_prompt = f"You are a helpful career coach. Answer clearly and briefly.{resume_context}\nUser message: {req.message}"
    reply = generate_text(system_prompt)
    return {"reply": reply}


@app.post("/chat/company/message")
def company_chat(req: CompanyChatRequest, authorization: Optional[str] = Header(None)):
    check_auth(req.company_user_id, authorization)
    company = ensure_company_context(req.company_user_id, req.company_id)
    job = get_company_job_posting(company["company_id"], req.job_posting_id) if req.job_posting_id else None
    kpis = get_company_kpis(company["company_id"], req.job_posting_id)
    reply = generate_text(build_company_chat_prompt(company, req.message, job=job, kpis=kpis))
    return {"reply": reply, "company": company, "job": job, "kpis": kpis}


@app.post("/chat/company/analyze-company")
def analyze_company(req: CompanyContextRequest, authorization: Optional[str] = Header(None)):
    check_auth(req.company_user_id, authorization)
    company = ensure_company_context(req.company_user_id, req.company_id)
    kpis = get_company_kpis(company["company_id"])
    prompt = build_company_chat_prompt(
        company,
        "Analyze our company profile for hiring attractiveness. Tell us what is strong, what is missing, and how to improve it.",
        kpis=kpis,
    )
    return {"analysis": generate_text(prompt), "company": company, "kpis": kpis}


@app.post("/chat/company/analyze-job-post")
def analyze_company_job_post(req: CompanyJobPostRequest, authorization: Optional[str] = Header(None)):
    check_auth(req.company_user_id, authorization)
    company = ensure_company_context(req.company_user_id, req.company_id)
    job = get_company_job_posting(company["company_id"], req.job_posting_id)
    return {"analysis": generate_text(build_job_post_analysis_prompt(company, job)), "company": company, "job": job}


@app.post("/chat/company/hiring-insights")
def company_hiring_insights(req: CompanyHiringInsightsRequest, authorization: Optional[str] = Header(None)):
    check_auth(req.company_user_id, authorization)
    company = ensure_company_context(req.company_user_id, req.company_id)
    kpis = get_company_kpis(company["company_id"], req.job_posting_id)
    prompt = build_company_chat_prompt(
        company,
        "Turn these hiring KPIs into useful recruiter insights. Include risks, bottlenecks, and recommended next actions.",
        kpis=kpis,
    )
    return {"insights": generate_text(prompt), "company": company, "kpis": kpis}


@app.post("/chat/company/generate-job-post")
def generate_company_job_post(req: CompanyGenerateJobPostRequest, authorization: Optional[str] = Header(None)):
    check_auth(req.company_user_id, authorization)
    company = ensure_company_context(req.company_user_id, req.company_id)
    prompt = f"""
You are an expert recruiter and job description writer.
Create a professional job post for this company.

{get_company_summary_for_prompt(company)}

Role: {req.role}
Level: {req.level}
Skills: {req.skills}
Work type: {req.work_type}
Location: {req.location}
Salary range: {req.salary_range}

Return:
1. Optimized title
2. Summary
3. Responsibilities
4. Qualifications
5. Nice-to-have skills
6. Benefits / attraction points
7. Interview screening questions
""".strip()
    return {"job_post": generate_text(prompt), "company": company}


@app.post("/chat/company/find-candidates")
def company_find_candidates(req: CompanyFindCandidatesRequest, authorization: Optional[str] = Header(None)):
    check_auth(req.company_user_id, authorization)
    company = ensure_company_context(req.company_user_id, req.company_id)
    job = get_company_job_posting(company["company_id"], req.job_posting_id)
    candidates = get_candidates_for_job(company["company_id"], req.job_posting_id, req.limit)
    if not candidates:
        return {"ranking": "No applicants found for this job posting.", "company": company, "job": job, "candidates": []}
    ranking = generate_text(build_candidates_prompt(company, job, candidates))
    public_candidates = [{k: v for k, v in c.items() if k != "resume_path"} for c in candidates]
    return {"ranking": ranking, "company": company, "job": job, "candidates": public_candidates}


@app.post("/clear-cache")
def clear_cache(x_admin_key: Optional[str] = Header(None, alias="X-Admin-API-Key")):
    if ADMIN_API_KEY:
        if not x_admin_key or x_admin_key != ADMIN_API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing X-Admin-API-Key header")
    get_resume_text_for_user.cache_clear()
    encode_query_cached.cache_clear()
    return {"status": "cache cleared"}

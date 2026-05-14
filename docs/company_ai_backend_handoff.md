# Company AI Chatbot – Backend Handoff

## Purpose
Add AI chatbot support for the company dashboard after company login.

Frontend page example:
`/dashboard/company/ai-chat`

The AI service now supports company-specific chatbot endpoints that can:
- Analyze company profile
- Analyze and improve job posts
- Generate job descriptions
- Show hiring insights
- Find and rank candidates for a job posting

---

## Important Authentication Rule
After company login, the frontend/backend should send one of these values to the AI API:

### Preferred
```json
{
  "company_user_id": "ApplicationUser.Id"
}
```

The AI service will resolve the company with:

```sql
SELECT TOP 1 CompanyID, Name, Industry, WebsiteURL, HeadquarterAddress, Location, LogoUrl, UserId
FROM Company
WHERE UserId = @company_user_id;
```

### Local testing only
```json
{
  "company_id": 1
}
```

---

## New API Endpoints

### 1. General company chat
`POST /chat/company/message`

Request:
```json
{
  "company_user_id": "USER_ID_FROM_LOGIN",
  "company_id": null,
  "job_posting_id": 15,
  "message": "How can we attract better candidates?"
}
```

Response:
```json
{
  "reply": "AI answer...",
  "company": {},
  "job": {},
  "kpis": {}
}
```

---

### 2. Analyze company profile
`POST /chat/company/analyze-company`

Request:
```json
{
  "company_user_id": "USER_ID_FROM_LOGIN"
}
```

---

### 3. Analyze job post
`POST /chat/company/analyze-job-post`

Request:
```json
{
  "company_user_id": "USER_ID_FROM_LOGIN",
  "job_posting_id": 15
}
```

The endpoint checks that this job belongs to the logged-in company:

```sql
SELECT TOP 1 JobID, Title, Description, Requirements, SalaryRange, PostedDate, IsActive, IsRemote, CompanyID, JobType
FROM JobPosting
WHERE JobID = @job_posting_id AND CompanyID = @company_id;
```

---

### 4. Hiring insights
`POST /chat/company/hiring-insights`

Request:
```json
{
  "company_user_id": "USER_ID_FROM_LOGIN",
  "job_posting_id": 15
}
```

`job_posting_id` is optional. Without it, the endpoint returns company-level hiring insights.

---

### 5. Generate job post
`POST /chat/company/generate-job-post`

Request:
```json
{
  "company_user_id": "USER_ID_FROM_LOGIN",
  "role": "Data Scientist",
  "level": "Senior",
  "skills": ["Python", "SQL", "Machine Learning"],
  "work_type": "Remote",
  "location": "Cairo",
  "salary_range": "20000-30000 EGP"
}
```

---

### 6. Find and rank candidates
`POST /chat/company/find-candidates`

Request:
```json
{
  "company_user_id": "USER_ID_FROM_LOGIN",
  "job_posting_id": 15,
  "limit": 10
}
```

The endpoint reads applications for the job and uses submitted/active resumes:

```sql
SELECT TOP @limit
    app.ApplicationID,
    applicant.ApplicantID,
    applicant.FirstName,
    applicant.LastName,
    applicant.Location,
    app.ApplicationStatus,
    app.AppliedDate,
    COALESCE(submittedResume.FilePath, activeResume.FilePath) AS ResumePath
FROM Application app
JOIN JobPosting jp ON jp.JobID = app.JobPostingID
JOIN Applicant applicant ON applicant.ApplicantID = app.ApplicantID
LEFT JOIN Resume submittedResume ON submittedResume.ResumeID = app.ResumeID
LEFT JOIN Resume activeResume ON activeResume.ApplicantID = applicant.ApplicantID AND activeResume.IsActive = 1
WHERE jp.CompanyID = @company_id AND jp.JobID = @job_posting_id
ORDER BY app.AppliedDate DESC;
```

---

## Database Changes Required?

### Required structural changes
No new tables are required for the company AI endpoints.

### Still required from the previous handoff
The `Resume` table must include:

```sql
ALTER TABLE Resume ADD IsActive BIT DEFAULT 0;
```

Business rule:
- Each applicant must have only one active resume.
- When uploading a new resume, deactivate previous resumes for that applicant.

```sql
UPDATE Resume SET IsActive = 0 WHERE ApplicantID = @ApplicantID;

INSERT INTO Resume (FileName, FilePath, UploadDate, IsActive, ApplicantID)
VALUES (@FileName, @FilePath, GETDATE(), 1, @ApplicantID);
```

### Recommended indexes
Run the SQL file:

```text
sql/company_ai_optional_indexes.sql
```

It includes:

```sql
CREATE INDEX IX_Company_UserId ON Company(UserId);
CREATE INDEX IX_JobPosting_CompanyID_JobID ON JobPosting(CompanyID, JobID);
CREATE INDEX IX_Application_JobPostingID_AppliedDate ON Application(JobPostingID, AppliedDate DESC);
CREATE INDEX IX_Resume_ApplicantID_IsActive_UploadDate ON Resume(ApplicantID, IsActive, UploadDate DESC);
```

---

## Resume FilePath Requirement
For candidate ranking and applicant matching, `Resume.FilePath` must be a reachable PDF or DOCX URL in production.

Recommended:
```text
https://<storage-account>.blob.core.windows.net/cvs/<file>.pdf
```

Avoid local Windows paths like:
```text
C:\Users\...
```

---

## Frontend Integration Notes
On `/dashboard/company/ai-chat`, send the logged-in company user id from auth/session.

Example:
```js
await fetch(`${AI_API_URL}/chat/company/message`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    company_user_id: session.user.id,
    job_posting_id: selectedJobId,
    message
  })
});
```

For local testing, open `index.html` from this package and enter either:
- `company_user_id`, or
- `company_id`

---

## Deployment Notes
The Dockerfile includes Microsoft ODBC Driver 18 so `pyodbc` can connect to Azure SQL.

Required environment variables:

```env
GEMINI_API_KEY=
SQL_SERVER=
SQL_DATABASE=
SQL_USERNAME=
SQL_PASSWORD=
SQL_DRIVER=ODBC Driver 18 for SQL Server
ALLOWED_ORIGINS=http://localhost:3000,https://graduation-project-sigma-pink.vercel.app
```

---

## Testing Checklist
- [ ] `GET /health` returns status ok
- [ ] `GET /health/app-db` connects to Azure SQL
- [ ] `POST /chat/company/analyze-company` works using `company_user_id`
- [ ] `POST /chat/company/analyze-job-post` works for a job owned by the company
- [ ] `POST /chat/company/hiring-insights` returns KPIs + AI insights
- [ ] `POST /chat/company/find-candidates` can read candidate resumes
- [ ] `Resume.FilePath` is reachable URL for PDF/DOCX files

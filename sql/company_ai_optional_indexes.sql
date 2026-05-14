-- Optional indexes for Company AI chatbot endpoints
-- These indexes improve company lookup, job ownership checks, and applicant ranking queries.

-- 1) Resolve logged-in company quickly using ApplicationUser.Id
CREATE INDEX IX_Company_UserId ON Company(UserId);

-- 2) Verify that a job belongs to the logged-in company
CREATE INDEX IX_JobPosting_CompanyID_JobID ON JobPosting(CompanyID, JobID);

-- 3) Read applications for a job quickly
CREATE INDEX IX_Application_JobPostingID_AppliedDate ON Application(JobPostingID, AppliedDate DESC);

-- 4) Read applicant active CV quickly
-- This is also required by the applicant AI service.
CREATE INDEX IX_Resume_ApplicantID_IsActive_UploadDate ON Resume(ApplicantID, IsActive, UploadDate DESC);

-- 5) If SavedJobs / JobMetric pages use these tables heavily, these are useful too.
CREATE INDEX IX_SavedJobs_JobPostingId ON SavedJobs(JobPostingId);
CREATE INDEX IX_JobMetric_JobID_LastUpdated ON JobMetric(JobID, LastUpdated DESC);

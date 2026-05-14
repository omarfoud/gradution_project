/*
Backend required SQL changes for Azure SQL Database.
Run this on the main application database before connecting the AI backend.
*/

-- 1) Add active resume flag if it does not exist
IF COL_LENGTH('Resume', 'IsActive') IS NULL
BEGIN
    ALTER TABLE Resume ADD IsActive BIT NOT NULL CONSTRAINT DF_Resume_IsActive DEFAULT 0;
END;
GO

-- 2) Recommended index for fast active CV lookup
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'idx_resume_active'
      AND object_id = OBJECT_ID('Resume')
)
BEGIN
    CREATE INDEX idx_resume_active
    ON Resume(ApplicantID, IsActive, UploadDate DESC);
END;
GO

-- 3) Business rule for uploading a new CV
-- Use this logic in the backend upload endpoint / service layer.
-- Replace variables with backend parameters.
/*
BEGIN TRANSACTION;

UPDATE Resume
SET IsActive = 0
WHERE ApplicantID = @ApplicantID;

INSERT INTO Resume (FileName, FilePath, UploadDate, IsActive, ApplicantID)
VALUES (@FileName, @FilePath, GETDATE(), 1, @ApplicantID);

COMMIT TRANSACTION;
*/

-- 4) Query used by AI backend
-- @UserId must be ApplicationUser.Id / Applicant.UserId value sent from frontend.
/*
SELECT TOP 1 r.FilePath
FROM Applicant a
JOIN Resume r ON r.ApplicantID = a.ApplicantID
WHERE a.UserId = @UserId AND r.IsActive = 1
ORDER BY r.UploadDate DESC;
*/

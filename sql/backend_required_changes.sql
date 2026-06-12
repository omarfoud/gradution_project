/*
Backend required SQL changes for Azure SQL Database.
Run this on the main application database before connecting the AI backend.
*/

-- 1) Add active resume flag if it does not exist.
-- Supports both ERD-style singular names and the deployed plural table names.
DECLARE @ResumeTable SYSNAME = CASE
    WHEN OBJECT_ID(N'dbo.Resume', N'U') IS NOT NULL THEN N'dbo.Resume'
    WHEN OBJECT_ID(N'dbo.Resumes', N'U') IS NOT NULL THEN N'dbo.Resumes'
    ELSE NULL
END;

IF @ResumeTable IS NOT NULL AND COL_LENGTH(@ResumeTable, 'IsActive') IS NULL
BEGIN
    DECLARE @AddIsActiveSql NVARCHAR(MAX) =
        N'ALTER TABLE ' + @ResumeTable + N' ADD IsActive BIT NOT NULL CONSTRAINT DF_' +
        REPLACE(REPLACE(@ResumeTable, N'dbo.', N''), N']', N'') + N'_IsActive DEFAULT 0;';
    EXEC sp_executesql @AddIsActiveSql;
END;
GO

-- 2) Recommended index for fast active CV lookup
DECLARE @ResumeTableForIndex SYSNAME = CASE
    WHEN OBJECT_ID(N'dbo.Resume', N'U') IS NOT NULL THEN N'dbo.Resume'
    WHEN OBJECT_ID(N'dbo.Resumes', N'U') IS NOT NULL THEN N'dbo.Resumes'
    ELSE NULL
END;

IF @ResumeTableForIndex IS NOT NULL
   AND COL_LENGTH(@ResumeTableForIndex, 'ApplicantID') IS NOT NULL
   AND COL_LENGTH(@ResumeTableForIndex, 'IsActive') IS NOT NULL
   AND COL_LENGTH(@ResumeTableForIndex, 'UploadDate') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1
        FROM sys.indexes
        WHERE name = 'idx_resume_active'
          AND object_id = OBJECT_ID(@ResumeTableForIndex)
   )
BEGIN
    DECLARE @CreateResumeIndexSql NVARCHAR(MAX) =
        N'CREATE INDEX idx_resume_active ON ' + @ResumeTableForIndex + N'(ApplicantID, IsActive, UploadDate DESC);';
    EXEC sp_executesql @CreateResumeIndexSql;
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
GO

-- 5) Add candidate match score to applications if it does not exist.
-- This maps to the .NET property: public int MatchScore { get; set; }
DECLARE @ApplicationTable SYSNAME = CASE
    WHEN OBJECT_ID(N'dbo.Application', N'U') IS NOT NULL THEN N'dbo.Application'
    WHEN OBJECT_ID(N'dbo.Applications', N'U') IS NOT NULL THEN N'dbo.Applications'
    ELSE NULL
END;

IF @ApplicationTable IS NOT NULL AND COL_LENGTH(@ApplicationTable, 'MatchScore') IS NULL
BEGIN
    DECLARE @AddMatchScoreSql NVARCHAR(MAX) =
        N'ALTER TABLE ' + @ApplicationTable + N' ADD MatchScore INT NOT NULL CONSTRAINT DF_' +
        REPLACE(REPLACE(@ApplicationTable, N'dbo.', N''), N']', N'') + N'_MatchScore DEFAULT 0;';
    EXEC sp_executesql @AddMatchScoreSql;
END;
GO

# Backend Handoff - Required Azure SQL & Deployment Changes

## الهدف
هذا الملف يوضح المطلوب من فريق الـ Backend حتى يكون النظام متوافقًا مع خدمة الـ AI Backend.
خدمة الـ AI ستأخذ `user_id` من الفرونت، ثم تجلب الـ CV النشط من Azure SQL، ثم تستخدمه في الترشيح والتحليل.

---

## 1) تعديل جدول Resume

يجب إضافة حقل `IsActive` في جدول `Resume`:

```sql
ALTER TABLE Resume ADD IsActive BIT DEFAULT 0;
```

الأفضل تشغيل سكريبت `sql/backend_required_changes.sql` المرفق لأنه يتحقق من وجود العمود والـ index قبل الإنشاء.

---

## 2) Business Rule عند رفع CV جديد

كل Applicant يجب أن يمتلك Resume واحد فقط Active.

عند رفع CV جديد:

```sql
BEGIN TRANSACTION;

UPDATE Resume
SET IsActive = 0
WHERE ApplicantID = @ApplicantID;

INSERT INTO Resume (FileName, FilePath, UploadDate, IsActive, ApplicantID)
VALUES (@FileName, @FilePath, GETDATE(), 1, @ApplicantID);

COMMIT TRANSACTION;
```

مهم تنفيذ هذا داخل Transaction حتى لا يحدث أكثر من CV نشط لنفس الـ Applicant.

---

## 3) Query التي يعتمد عليها AI Backend

الـ AI Backend يستخدم هذا الاستعلام لجلب الـ CV النشط بناءً على UserId:

```sql
SELECT TOP 1 r.FilePath
FROM Applicant a
JOIN Resume r ON r.ApplicantID = a.ApplicantID
WHERE a.UserId = @UserId AND r.IsActive = 1
ORDER BY r.UploadDate DESC;
```

حسب الـ ERD الحالي، جدول `Applicant` يحتوي على `UserId` مربوط بـ `ApplicationUser.Id`.

---

## 4) Index Optimization

يجب إنشاء index لتحسين سرعة query جلب الـ CV:

```sql
CREATE INDEX idx_resume_active
ON Resume(ApplicantID, IsActive, UploadDate DESC);
```

---

## 5) Azure SQL Deployment

المطلوب من الـ Backend:

1. رفع قاعدة البيانات على Azure SQL Database.
2. تفعيل Allow Azure services للوصول من الخدمات الخارجية.
3. التأكد من أن بيانات الاتصال متاحة كـ Environment Variables وليس داخل الكود.
4. إرسال القيم التالية لفريق الـ AI بشكل آمن:

```env
SQL_SERVER=your-server.database.windows.net
SQL_DATABASE=your_database_name
SQL_USERNAME=your_sql_username
SQL_PASSWORD=your_sql_password
SQL_PORT=1433
```

---

## 6) Resume FilePath Requirement

`Resume.FilePath` يجب أن يكون رابط PDF أو DOCX قابل للوصول من AI Backend.

الأفضل:

```text
https://your-storage.blob.core.windows.net/resumes/user-cv.pdf
```

غير مقبول في الإنتاج:

```text
C:\Users\...\cv.pdf
```

لأن AI Backend سيكون داخل Docker أو Cloud ولن يستطيع قراءة مسار محلي على جهاز آخر.

---

## 7) Docker Requirement

الـ AI Backend يستخدم `pyodbc` للاتصال بـ Azure SQL، لذلك Dockerfile يحتوي على Microsoft ODBC Driver 18:

```bash
ACCEPT_EULA=Y apt-get install -y msodbcsql18
```

---

## 8) AI Backend Endpoints

بعد تشغيل النظام:

- `GET /health` للتأكد من تحميل FAISS و SQLite و Gemini config.
- `GET /health/app-db` لاختبار اتصال Azure SQL.
- `POST /recommend-matches` يأخذ `user_id` ويرجع وظائف مناسبة للـ CV.
- `POST /analyze-job-id` يأخذ `user_id` و `job_id` ويحلل مدى مناسبة الـ CV للوظيفة.
- `POST /search` للبحث العام في الوظائف.
- `POST /chat` للأسئلة العامة.

---

## 9) Checklist قبل التسليم

- [ ] Azure SQL Database جاهزة.
- [ ] `Resume.IsActive` موجود.
- [ ] Business rule مطبقة عند رفع CV جديد.
- [ ] `idx_resume_active` معمول.
- [ ] `Resume.FilePath` عبارة عن URL للـ PDF/DOCX.
- [ ] Environment Variables متاحة للـ AI Backend.
- [ ] `/health/app-db` يرجع status ok.
- [ ] تجربة user_id فعلي له CV active.

---

## 10) ملاحظات مهمة

- لا يتم رفع `.env` على GitHub.
- ملفات `jobs.db` و `jobs.index` لا يتم رفعها على GitHub غالبًا لأنها كبيرة، ويتم إنشاؤها محليًا بواسطة `python ingest.py`.
- يجب وضع `job_descriptions.csv` في root project قبل تشغيل ingestion.

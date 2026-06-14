# Artifact Setup Guide — Hugging Face (Free)

## The Problem

`jobs.db` (~700MB) and `jobs.index` (~2.5GB) are generated from the 1.6GB CSV.
They cannot be committed to GitHub (100MB limit) or stored in the SmarterASP.NET
SQL Server (it's a database, not a file host). Total size: ~3.2GB.

## Solution: Hugging Face Dataset Repository (Free, No Subscription)

Hugging Face hosts files of any size for free. It's the standard tool for ML
artifact storage and has a Python SDK with direct download support.

---

## Step 1: Run ingest.py on your local machine (one time only)

```bash
# Make sure job_descriptions.csv is in the project root (~1.6GB)
ls -lh job_descriptions.csv

# Install deps and run ingestion (30–90 min on CPU)
pip install -r requirements.txt
RESET_DB=true python ingest.py

# Verify output
ls -lh jobs.db jobs.index
# jobs.db    → ~700MB
# jobs.index → ~2.5GB
```

---

## Step 2: Create a free Hugging Face account

1. Go to **https://huggingface.co** → Sign Up (free, no credit card)
2. Go to **https://huggingface.co/settings/tokens** → New token
   - Name: `jobify-deploy`
   - Role: **Write**
   - Copy the token (starts with `hf_`)

---

## Step 3: Create a private dataset repo and upload

```bash
pip install huggingface_hub

python << 'EOF'
from huggingface_hub import HfApi

HF_USERNAME = "your-hf-username"     # change this
HF_TOKEN    = "hf_your_token_here"   # change this
REPO_ID     = f"{HF_USERNAME}/jobify-artifacts"

api = HfApi()

# Create private repo (only needed once)
api.create_repo(REPO_ID, repo_type="dataset", private=True, token=HF_TOKEN)
print(f"Repo created: {REPO_ID}")

# Upload jobs.db (~700MB — takes a few minutes)
print("Uploading jobs.db...")
api.upload_file(
    path_or_fileobj="jobs.db",
    path_in_repo="jobs.db",
    repo_id=REPO_ID,
    repo_type="dataset",
    token=HF_TOKEN,
)
print("✅ jobs.db uploaded")

# Upload jobs.index (~2.5GB — takes 10–20 min depending on internet)
print("Uploading jobs.index...")
api.upload_file(
    path_or_fileobj="jobs.index",
    path_in_repo="jobs.index",
    repo_id=REPO_ID,
    repo_type="dataset",
    token=HF_TOKEN,
)
print("✅ jobs.index uploaded")
print("Done! Both files are on Hugging Face.")
EOF
```

---

## Step 4: Add credentials to your `.env`

```env
HF_REPO_ID=your-hf-username/jobify-artifacts
HF_TOKEN=hf_your_token_here
```

The container will auto-download both files on first startup (~15–30 min
depending on server internet speed). Subsequent restarts use the cached files.

---

## Step 5: For local development (skip the download)

Instead of downloading, just volume-mount the files. Uncomment in `docker-compose.yml`:

```yaml
volumes:
  - ./jobs.db:/app/jobs.db
  - ./jobs.index:/app/jobs.index
```

---

## Artifact Lifecycle

| Event | Action |
|---|---|
| First deployment | Container downloads from Hugging Face automatically |
| Code change | Rebuild image (fast, ~500MB — no data included) |
| CSV dataset update | Re-run `ingest.py` locally, re-upload to Hugging Face |
| Token rotation | Generate new HF token, update `HF_TOKEN` in `.env` |

---

## Cost

**Free.** Hugging Face has no storage fees for dataset repositories. The only
limit is that very large repos (>50GB) may require LFS, which is still free
for standard use. Your 3.2GB is well within the free tier.

---

## Why Not SmarterASP.NET File Hosting?

SmarterASP.NET is a Windows shared web host — it provides SQL Server and
web space for `.aspx`/`.NET` apps, but:
- No programmatic file download API
- Large binary files would hit their "soft limit" instantly
- Download speeds are throttled on shared plans
- Not designed for blob/artifact storage

Hugging Face is purpose-built for exactly this use case.

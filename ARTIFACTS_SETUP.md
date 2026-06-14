# Embedding Artifacts Setup Guide

## The Problem

The FAISS index (`jobs.index`, ~2.5GB) and SQLite database (`jobs.db`, ~700MB) are
generated from the 1.6GB CSV dataset. They cannot be committed to GitHub (100MB limit)
or stored in the SQL database (subscription limit).

**Total artifact size: ~3.2GB**

## Recommended Solution: Azure Blob Storage

You already have an Azure subscription for the SQL database. Azure Blob Storage costs
roughly **$0.06/month** for 3.2GB — essentially free.

### Step 1: Run ingestion once on your local machine

```bash
# Make sure you have the CSV file
ls job_descriptions.csv   # should be ~1.6GB

# Install dependencies
pip install -r requirements.txt

# Run ingestion (takes 30–90 min on CPU depending on machine)
RESET_DB=true python ingest.py

# Verify output
ls -lh jobs.db jobs.index
# jobs.db   → ~700MB
# jobs.index → ~2.5GB
```

### Step 2: Upload to Azure Blob Storage

1. Go to [portal.azure.com](https://portal.azure.com)
2. Open your Storage Account (or create one: **Storage Accounts → Create**)
3. Create a container called `ai-artifacts` (private access)
4. Upload both files:
   ```bash
   # Using Azure CLI (install with: pip install azure-cli)
   az storage blob upload \
     --account-name YOUR_STORAGE_ACCOUNT \
     --container-name ai-artifacts \
     --name jobs.db \
     --file jobs.db

   az storage blob upload \
     --account-name YOUR_STORAGE_ACCOUNT \
     --container-name ai-artifacts \
     --name jobs.index \
     --file jobs.index
   ```

### Step 3: Generate SAS URLs (expire in 1 year)

```bash
# Generate SAS URL for jobs.db
az storage blob generate-sas \
  --account-name YOUR_STORAGE_ACCOUNT \
  --container-name ai-artifacts \
  --name jobs.db \
  --permissions r \
  --expiry 2027-01-01 \
  --full-uri \
  --output tsv

# Generate SAS URL for jobs.index
az storage blob generate-sas \
  --account-name YOUR_STORAGE_ACCOUNT \
  --container-name ai-artifacts \
  --name jobs.index \
  --permissions r \
  --expiry 2027-01-01 \
  --full-uri \
  --output tsv
```

### Step 4: Add URLs to your `.env`

```env
ARTIFACTS_URL_DB=https://youraccount.blob.core.windows.net/ai-artifacts/jobs.db?sv=...
ARTIFACTS_URL_INDEX=https://youraccount.blob.core.windows.net/ai-artifacts/jobs.index?sv=...
```

The container will auto-download both files on first startup if they are missing.
Download happens once and is cached on the container's disk for subsequent restarts.

---

## Alternative: Local Development (Volume Mount)

For local development, skip the Azure setup and use volume mounts instead:

```yaml
# In docker-compose.yml, uncomment the volumes section:
volumes:
  - ./jobs.db:/app/jobs.db
  - ./jobs.index:/app/jobs.index
```

Then run `docker compose up` with the files in your project root.

---

## Artifact Lifecycle

| Event | Action |
|---|---|
| First deployment | Download from Azure Blob on container start |
| Code change | Rebuild image (fast, ~500MB — no data included) |
| CSV dataset update | Re-run `ingest.py`, re-upload to Azure Blob |
| SAS URL expiry | Generate new SAS URLs, update `.env` |

---

## Why Not Bake Into Docker Image?

The previous approach (`RUN test -f /app/jobs.db`) baked the 3.2GB files into the
image, making it ~4–5GB total. Problems:

- Every code change requires pushing 4–5GB to the registry
- Docker Hub free tier has pull rate limits for large images
- The `build` step fails for anyone who doesn't have the files locally

The new approach keeps the image at ~500MB and pulls data separately.

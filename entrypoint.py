import os
import sys
import subprocess

DB_PATH    = os.getenv("DB_PATH", "jobs.db")
INDEX_PATH = os.getenv("INDEX_PATH", "jobs.index")

# ---------------------------------------------------------------------------
# Artifact source — choose ONE by setting env vars in .env:
#
#   Option A: Hugging Face (recommended — free, no subscription needed)
#     HF_REPO_ID = "your-hf-username/jobify-artifacts"
#     HF_TOKEN   = "hf_xxxxxxxxxxxx"   (from huggingface.co/settings/tokens)
#
#   Option B: Any direct HTTPS URL (Azure Blob SAS, Google Drive, etc.)
#     ARTIFACTS_URL_DB    = "https://..."
#     ARTIFACTS_URL_INDEX = "https://..."
#
#   Option C: Volume mount (local dev) — set neither; mount files as volumes.
# ---------------------------------------------------------------------------
HF_REPO_ID          = os.getenv("HF_REPO_ID", "")
HF_TOKEN            = os.getenv("HF_TOKEN", "")
ARTIFACTS_URL_DB    = os.getenv("ARTIFACTS_URL_DB", "")
ARTIFACTS_URL_INDEX = os.getenv("ARTIFACTS_URL_INDEX", "")


# ---------------------------------------------------------------------------
# 1. Safeguard: reject empty directories Docker creates on missing volume mounts
# ---------------------------------------------------------------------------
for path, label in [(DB_PATH, "jobs.db"), (INDEX_PATH, "jobs.index")]:
    if os.path.exists(path) and not os.path.isfile(path):
        print(
            f"CRITICAL ERROR: '{path}' exists but is a directory, not a file!\n"
            f"Fix: place the real {label} in the project root before building.",
            file=sys.stderr, flush=True,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# 2. Download missing artifacts
# ---------------------------------------------------------------------------
def download_from_hf(repo_id: str, filename: str, dest: str, token: str) -> None:
    print(f"Downloading {filename} from Hugging Face ({repo_id})...", flush=True)
    try:
        from huggingface_hub import hf_hub_download
        tmp = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            repo_type="dataset",
            token=token or None,
            local_dir="/tmp/hf_artifacts",
        )
        import shutil
        shutil.move(tmp, dest)
        size_mb = os.path.getsize(dest) / 1024 / 1024
        print(f"✅ {filename} downloaded ({size_mb:.0f} MB)", flush=True)
    except Exception as exc:
        print(
            f"CRITICAL ERROR: Failed to download {filename} from Hugging Face: {exc}\n"
            f"Check HF_REPO_ID and HF_TOKEN in your .env file.",
            file=sys.stderr, flush=True,
        )
        sys.exit(1)


def download_from_url(url: str, dest: str, label: str) -> None:
    print(f"Downloading {label} from URL...", flush=True)
    try:
        import urllib.request
        tmp = dest + ".tmp"
        urllib.request.urlretrieve(url, tmp)
        os.rename(tmp, dest)
        size_mb = os.path.getsize(dest) / 1024 / 1024
        print(f"✅ {label} downloaded ({size_mb:.0f} MB)", flush=True)
    except Exception as exc:
        print(
            f"CRITICAL ERROR: Failed to download {label}: {exc}\n"
            f"Check ARTIFACTS_URL_DB / ARTIFACTS_URL_INDEX in your .env file.",
            file=sys.stderr, flush=True,
        )
        sys.exit(1)


missing_db    = not os.path.isfile(DB_PATH)
missing_index = not os.path.isfile(INDEX_PATH)

if missing_db or missing_index:
    if HF_REPO_ID:
        # Option A: Hugging Face
        if missing_db:
            download_from_hf(HF_REPO_ID, "jobs.db", DB_PATH, HF_TOKEN)
        if missing_index:
            download_from_hf(HF_REPO_ID, "jobs.index", INDEX_PATH, HF_TOKEN)

    elif ARTIFACTS_URL_DB and ARTIFACTS_URL_INDEX:
        # Option B: Direct URLs
        if missing_db:
            download_from_url(ARTIFACTS_URL_DB, DB_PATH, "jobs.db")
        if missing_index:
            download_from_url(ARTIFACTS_URL_INDEX, INDEX_PATH, "jobs.index")

    else:
        print(
            "CRITICAL ERROR: Search artifacts (jobs.db / jobs.index) are missing "
            "and no download source is configured.\n\n"
            "Choose one of:\n"
            "  A) Hugging Face (free):  set HF_REPO_ID and HF_TOKEN in .env\n"
            "  B) Direct URL:           set ARTIFACTS_URL_DB and ARTIFACTS_URL_INDEX in .env\n"
            "  C) Local dev:            volume-mount jobs.db and jobs.index via docker-compose\n\n"
            "See ARTIFACTS_SETUP.md for full instructions.",
            file=sys.stderr, flush=True,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# 3. Start the application
# ---------------------------------------------------------------------------
print("Starting FastAPI via Uvicorn...", flush=True)
subprocess.run(
    ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
    check=True,
)

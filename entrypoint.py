import os
import sys
import subprocess

DB_PATH = os.getenv("DB_PATH", "jobs.db")
INDEX_PATH = os.getenv("INDEX_PATH", "jobs.index")
ARTIFACTS_URL_DB = os.getenv("ARTIFACTS_URL_DB", "")      # Azure Blob SAS URL for jobs.db
ARTIFACTS_URL_INDEX = os.getenv("ARTIFACTS_URL_INDEX", "") # Azure Blob SAS URL for jobs.index

# ---------------------------------------------------------------------------
# 1. Safeguard: reject empty directories that Docker sometimes creates
#    when a volume mount target doesn't exist on the host.
# ---------------------------------------------------------------------------
for path, label in [(DB_PATH, "jobs.db"), (INDEX_PATH, "jobs.index")]:
    if os.path.exists(path) and not os.path.isfile(path):
        print(
            f"CRITICAL ERROR: '{path}' exists but is a directory, not a file!\n"
            f"Fix: put the real {label} in the project root and rebuild.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Auto-download from Azure Blob Storage when files are missing.
#    Set ARTIFACTS_URL_DB and ARTIFACTS_URL_INDEX to SAS URLs in your .env.
# ---------------------------------------------------------------------------
def download_artifact(url: str, dest: str, label: str) -> None:
    print(f"Downloading {label} from Azure Blob Storage...", flush=True)
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
            f"Set ARTIFACTS_URL_DB / ARTIFACTS_URL_INDEX in .env with valid SAS URLs.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)


missing_db = not os.path.isfile(DB_PATH)
missing_index = not os.path.isfile(INDEX_PATH)

if missing_db or missing_index:
    if not ARTIFACTS_URL_DB or not ARTIFACTS_URL_INDEX:
        print(
            f"CRITICAL ERROR: Search artifacts missing and no download URLs configured.\n"
            f"Either:\n"
            f"  A) Place jobs.db and jobs.index in the project root, OR\n"
            f"  B) Set ARTIFACTS_URL_DB and ARTIFACTS_URL_INDEX env vars to Azure Blob SAS URLs.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    if missing_db:
        download_artifact(ARTIFACTS_URL_DB, DB_PATH, "jobs.db")
    if missing_index:
        download_artifact(ARTIFACTS_URL_INDEX, INDEX_PATH, "jobs.index")

# ---------------------------------------------------------------------------
# 3. Start the application server.
# ---------------------------------------------------------------------------
print("Starting FastAPI Application via Uvicorn...", flush=True)
subprocess.run(
    ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
    check=True,
)

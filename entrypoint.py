import os
import sys
import subprocess

DB_PATH = os.getenv("DB_PATH", "jobs.db")
INDEX_PATH = os.getenv("INDEX_PATH", "jobs.index")

# 1. Safeguard against Docker creating directories when host files are missing
if os.path.exists(DB_PATH) and not os.path.isfile(DB_PATH):
    print(
        f"CRITICAL ERROR: '{DB_PATH}' exists but is a directory, not a file!\n"
        f"This occurs because Docker mounts non-existent host paths as directories.\n"
        f"To fix this:\n"
        f"  1. Stop your containers ('docker-compose down')\n"
        f"  2. Remove the empty '{DB_PATH}' directory created on the host\n"
        f"  3. Run 'python ingest.py' on your host to build the actual database file\n"
        f"  4. Restart your docker containers",
        file=sys.stderr,
        flush=True
    )
    sys.exit(1)

if os.path.exists(INDEX_PATH) and not os.path.isfile(INDEX_PATH):
    print(
        f"CRITICAL ERROR: '{INDEX_PATH}' exists but is a directory, not a file!\n"
        f"This occurs because Docker mounts non-existent host paths as directories.\n"
        f"To fix this:\n"
        f"  1. Stop your containers ('docker-compose down')\n"
        f"  2. Remove the empty '{INDEX_PATH}' directory created on the host\n"
        f"  3. Run 'python ingest.py' on your host to build the actual index file\n"
        f"  4. Restart your docker containers",
        file=sys.stderr,
        flush=True
    )
    sys.exit(1)

# 2. Alert the operator if files are completely missing
if not os.path.isfile(DB_PATH) or not os.path.isfile(INDEX_PATH):
    print(
        f"WARNING: SQLite database ('{DB_PATH}') or FAISS index ('{INDEX_PATH}') is missing!\n"
        f"The applicant recommendation and matching endpoints will return HTTP 503 fallbacks.\n"
        f"Please run 'python ingest.py' to generate these files.",
        file=sys.stderr,
        flush=True
    )

# 3. Start the uvicorn application server
print("Starting FastAPI Application via Uvicorn...", flush=True)
cmd = [
    "uvicorn",
    "main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000"
]
subprocess.run(cmd, check=True)

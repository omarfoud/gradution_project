import os
import sys
import subprocess

DB_PATH = os.getenv("DB_PATH", "jobs.db")
INDEX_PATH = os.getenv("INDEX_PATH", "jobs.index")

# 1. Safeguard against invalid local search artifacts.
if os.path.exists(DB_PATH) and not os.path.isfile(DB_PATH):
    print(
        f"CRITICAL ERROR: '{DB_PATH}' exists but is a directory, not a file!\n"
        f"The Docker image must contain the real jobs.db file.\n"
        f"To fix this:\n"
        f"  1. Put jobs.db in the project root beside Dockerfile\n"
        f"  2. Rebuild the image with: docker compose build\n"
        f"  3. Start it with: docker compose up",
        file=sys.stderr,
        flush=True
    )
    sys.exit(1)

if os.path.exists(INDEX_PATH) and not os.path.isfile(INDEX_PATH):
    print(
        f"CRITICAL ERROR: '{INDEX_PATH}' exists but is a directory, not a file!\n"
        f"The Docker image must contain the real jobs.index file.\n"
        f"To fix this:\n"
        f"  1. Put jobs.index in the project root beside Dockerfile\n"
        f"  2. Rebuild the image with: docker compose build\n"
        f"  3. Start it with: docker compose up",
        file=sys.stderr,
        flush=True
    )
    sys.exit(1)

# 2. Fail fast if the image was built without the local search files.
if not os.path.isfile(DB_PATH) or not os.path.isfile(INDEX_PATH):
    print(
        f"CRITICAL ERROR: SQLite database ('{DB_PATH}') or FAISS index ('{INDEX_PATH}') is missing!\n"
        f"Put jobs.db and jobs.index in the project root before building the Docker image.",
        file=sys.stderr,
        flush=True
    )
    sys.exit(1)

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

import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import urlretrieve

from huggingface_hub import hf_hub_download

DB_PATH = os.getenv("DB_PATH", "/app/artifacts/jobs.db")
INDEX_PATH = os.getenv("INDEX_PATH", "/app/artifacts/jobs.index")

HF_REPO_ID = os.getenv("HF_REPO_ID", "")
HF_REPO_TYPE = os.getenv("HF_REPO_TYPE", "dataset")
HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_DB_FILENAME = os.getenv("HF_DB_FILENAME", "jobs.db")
HF_INDEX_FILENAME = os.getenv("HF_INDEX_FILENAME", "jobs.index")
HF_ARTIFACT_DIR = os.getenv("HF_ARTIFACT_DIR", "/app/artifacts")

ARTIFACTS_URL_DB = os.getenv("ARTIFACTS_URL_DB", "")
ARTIFACTS_URL_INDEX = os.getenv("ARTIFACTS_URL_INDEX", "")


def fail(message: str) -> None:
    print(message, file=sys.stderr, flush=True)
    sys.exit(1)


def validate_file_path(path: str, label: str) -> None:
    if os.path.exists(path) and not os.path.isfile(path):
        fail(
            f"CRITICAL ERROR: '{path}' exists but is a directory, not a file!\n"
            f"Expected the real {label} file."
        )


def download_from_hf(filename: str, target_path: str, label: str) -> str:
    artifact_dir = Path(HF_ARTIFACT_DIR)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    print(f"{label} missing. Downloading '{filename}' from Hugging Face repo '{HF_REPO_ID}'...", flush=True)
    try:
        downloaded_path = hf_hub_download(
            repo_id=HF_REPO_ID,
            filename=filename,
            repo_type=HF_REPO_TYPE,
            token=HF_TOKEN or None,
            local_dir=str(artifact_dir),
        )
    except Exception as exc:
        fail(f"CRITICAL ERROR: Failed to download {label} from Hugging Face: {exc}")

    downloaded_path = str(Path(downloaded_path).resolve())
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    if str(target.parent.resolve()) != str(artifact_dir.resolve()) and not target.exists():
        shutil.copyfile(downloaded_path, target)
        return str(target.resolve())

    return downloaded_path


def download_from_url(url: str, target_path: str, label: str) -> str:
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_suffix(target.suffix + ".tmp")

    print(f"{label} missing. Downloading from direct URL...", flush=True)
    try:
        urlretrieve(url, temp_path)
        os.replace(temp_path, target)
    except Exception as exc:
        fail(f"CRITICAL ERROR: Failed to download {label} from direct URL: {exc}")

    return str(target.resolve())


def ensure_artifact(path: str, label: str, hf_filename: str, direct_url: str) -> str:
    validate_file_path(path, label)
    if os.path.isfile(path):
        return path

    if HF_REPO_ID:
        return download_from_hf(hf_filename, path, label)

    if direct_url:
        return download_from_url(direct_url, path, label)

    fail(
        f"CRITICAL ERROR: {label} is missing at '{path}' and no artifact source is configured.\n\n"
        "Set HF_REPO_ID and HF_TOKEN in .env for Hugging Face download, or set direct URLs:\n"
        "  ARTIFACTS_URL_DB=https://...\n"
        "  ARTIFACTS_URL_INDEX=https://...\n\n"
        "See ARTIFACTS_SETUP.md for full instructions."
    )


DB_PATH = ensure_artifact(DB_PATH, "SQLite database", HF_DB_FILENAME, ARTIFACTS_URL_DB)
INDEX_PATH = ensure_artifact(INDEX_PATH, "FAISS index", HF_INDEX_FILENAME, ARTIFACTS_URL_INDEX)
os.environ["DB_PATH"] = DB_PATH
os.environ["INDEX_PATH"] = INDEX_PATH

print("Starting FastAPI via Uvicorn...", flush=True)
subprocess.run(
    ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
    check=True,
)

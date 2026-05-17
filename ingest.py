import logging
import math
import os
import sqlite3
from pathlib import Path

import faiss
import pandas as pd
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("ingest")

CSV_PATH = os.getenv("CSV_PATH", "job_descriptions.csv")
DB_PATH = os.getenv("DB_PATH", "jobs.db")
INDEX_PATH = os.getenv("INDEX_PATH", "jobs.index")
MODEL_NAME = os.getenv("MODEL_NAME", "all-MiniLM-L6-v2")
DEVICE = os.getenv("DEVICE", "cpu")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "5000"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "64"))
NLIST = int(os.getenv("FAISS_NLIST", "1000"))
RESET_DB = os.getenv("RESET_DB", "true").lower() in {"1", "true", "yes", "y"}

KEEP_COLUMNS = [
    "Job Id",
    "Job Title",
    "Company",
    "Job Description",
    "Qualifications",
    "Responsibilities",
    "skills",
    "Experience",
    "location",
    "Work Type",
    "Salary Range",
]


def build_embed_text(chunk: pd.DataFrame) -> pd.Series:
    return (
        chunk["Job Title"].fillna("").astype(str) + " "
        + chunk["skills"].fillna("").astype(str) + " "
        + chunk["Qualifications"].fillna("").astype(str) + " "
        + chunk["Responsibilities"].fillna("").astype(str) + " "
        + chunk["Job Description"].fillna("").astype(str).str.slice(0, 900) + " "
        + chunk["Experience"].fillna("").astype(str) + " "
        + chunk["location"].fillna("").astype(str) + " "
        + chunk["Work Type"].fillna("").astype(str)
    ).str.strip()


def validate_columns(df_columns) -> None:
    missing = [column for column in KEEP_COLUMNS if column not in df_columns]
    if missing:
        raise ValueError(f"Missing required CSV columns: {missing}")


def create_jobs_table(cursor: sqlite3.Cursor) -> None:
    if RESET_DB:
        cursor.execute("DROP TABLE IF EXISTS jobs")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            faiss_id INTEGER PRIMARY KEY,
            job_id INTEGER UNIQUE,
            title TEXT,
            company TEXT,
            description TEXT,
            qualifications TEXT,
            responsibilities TEXT,
            skills TEXT,
            experience TEXT,
            location TEXT,
            work_type TEXT,
            salary_range TEXT
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_job_id ON jobs(job_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_location ON jobs(location)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_work_type ON jobs(work_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_experience ON jobs(experience)")


def count_rows(csv_path: str) -> int:
    with open(csv_path, "r", encoding="utf-8", errors="ignore") as csv_file:
        return max(0, sum(1 for _ in csv_file) - 1)


def setup_database() -> None:
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"CSV file not found: {CSV_PATH}")

    logger.info("Loading CSV header from %s", CSV_PATH)
    sample = pd.read_csv(CSV_PATH, nrows=5)
    validate_columns(sample.columns)

    logger.info("Loading embedding model: %s on %s", MODEL_NAME, DEVICE)
    model = SentenceTransformer(MODEL_NAME, device=DEVICE)
    embedding_dim = model.get_sentence_embedding_dimension()

    quantizer = faiss.IndexFlatIP(embedding_dim)
    index = faiss.IndexIVFFlat(quantizer, embedding_dim, NLIST, faiss.METRIC_INNER_PRODUCT)

    if RESET_DB:
        for path in [DB_PATH, INDEX_PATH]:
            if Path(path).exists():
                logger.info("RESET_DB=true, removing old file: %s", path)
                Path(path).unlink()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    create_jobs_table(cursor)
    conn.commit()

    total_rows = count_rows(CSV_PATH)
    total_chunks = max(1, math.ceil(total_rows / CHUNK_SIZE))
    logger.info("Processing %s rows in about %s chunks", total_rows, total_chunks)

    csv_reader = pd.read_csv(CSV_PATH, usecols=KEEP_COLUMNS, chunksize=CHUNK_SIZE)
    faiss_id_counter = 0
    trained = False
    chunks_since_commit = 0

    progress = tqdm(csv_reader, total=total_chunks, unit="chunk", desc="Indexing jobs", ncols=100)
    for chunk_index, chunk in enumerate(progress, start=1):
        chunk = chunk.fillna("")
        chunk["embed_text"] = build_embed_text(chunk)
        chunk = chunk[chunk["embed_text"].str.strip() != ""].copy()
        if chunk.empty:
            continue

        valid_rows = []
        for _, row in chunk.iterrows():
            raw_job_id = str(row["Job Id"]).strip()
            if not raw_job_id:
                continue
            try:
                job_id = int(float(raw_job_id))
            except ValueError:
                logger.warning("Skipping row with invalid Job Id: %s", raw_job_id)
                continue

            valid_rows.append(
                {
                    "job_id": job_id,
                    "title": str(row["Job Title"]),
                    "company": str(row["Company"]),
                    "description": str(row["Job Description"]),
                    "qualifications": str(row["Qualifications"]),
                    "responsibilities": str(row["Responsibilities"]),
                    "skills": str(row["skills"]),
                    "experience": str(row["Experience"]),
                    "location": str(row["location"]),
                    "work_type": str(row["Work Type"]),
                    "salary_range": str(row["Salary Range"]),
                    "embed_text": str(row["embed_text"]),
                }
            )

        if not valid_rows:
            continue

        valid_df = pd.DataFrame(valid_rows)
        embeddings = model.encode(
            valid_df["embed_text"].tolist(),
            batch_size=BATCH_SIZE,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype("float32")
        faiss.normalize_L2(embeddings)

        if not trained:
            if len(embeddings) < max(100, min(NLIST, 1000)):
                raise ValueError("First usable chunk is too small for FAISS training. Increase CHUNK_SIZE.")
            train_size = min(len(embeddings), max(NLIST * 5, 1000))
            index.train(embeddings[:train_size])
            trained = True
            logger.info("FAISS index trained with %s vectors", train_size)

        index.add(embeddings)

        sql_data = []
        for row in valid_rows:
            sql_data.append(
                (
                    faiss_id_counter,
                    row["job_id"],
                    row["title"],
                    row["company"],
                    row["description"],
                    row["qualifications"],
                    row["responsibilities"],
                    row["skills"],
                    row["experience"],
                    row["location"],
                    row["work_type"],
                    row["salary_range"],
                )
            )
            faiss_id_counter += 1

        cursor.executemany(
            """
            INSERT OR REPLACE INTO jobs (
                faiss_id, job_id, title, company, description,
                qualifications, responsibilities, skills, experience,
                location, work_type, salary_range
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            sql_data,
        )

        chunks_since_commit += 1
        if chunks_since_commit >= 5:
            conn.commit()
            chunks_since_commit = 0

        progress.set_postfix(indexed=faiss_id_counter)
        if chunk_index % 10 == 0:
            logger.info("Progress: chunk %s/%s, indexed jobs=%s", chunk_index, total_chunks, faiss_id_counter)

    if not trained:
        conn.close()
        raise ValueError("FAISS index was not trained. Check CSV content and required columns.")

    conn.commit()
    conn.execute("PRAGMA optimize")
    faiss.write_index(index, INDEX_PATH)
    conn.close()
    logger.info("Ingestion complete. %s jobs indexed. DB=%s INDEX=%s", faiss_id_counter, DB_PATH, INDEX_PATH)


if __name__ == "__main__":
    setup_database()

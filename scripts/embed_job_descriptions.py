import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from sqlalchemy import text  # noqa: E402
from backend.db.repo import SessionLocal, engine  # noqa: E402
from backend.db.models import Job  # noqa: E402
from backend.utils.embedding import embed_text  # noqa: E402


def ensure_column_exists() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE jobs "
                "ADD COLUMN IF NOT EXISTS description_embedding vector(1536);"
            )
        )


def fetch_jobs(session, include_existing: bool, limit: int | None):
    query = session.query(Job)
    if not include_existing:
        query = query.filter(Job.description_embedding.is_(None))
    query = query.order_by(Job.id.asc())
    if limit:
        query = query.limit(limit)
    return query.all()


def upsert_embedding(session, job: Job) -> bool:
    if not (job.description or "").strip():
        return False

    full_text = f"{job.title or ''}\n{job.company or ''}\n{job.description or ''}"
    vector = embed_text(full_text)

    job.description_embedding = vector
    session.commit()
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate and store embeddings for job descriptions."
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Recompute embeddings even if a job already has one.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of jobs to process.",
    )
    args = parser.parse_args()

    load_dotenv()
    ensure_column_exists()

    session = SessionLocal()
    try:
        jobs = fetch_jobs(session, args.include_existing, args.limit)
        if not jobs:
            print("No jobs to process.")
            return

        processed = 0
        skipped = 0
        for job in jobs:
            try:
                if upsert_embedding(session, job):
                    processed += 1
                else:
                    skipped += 1
            except Exception as exc:
                skipped += 1
                print(f"[ERR] Job {job.id} failed: {exc}")

        print(f"Embeddings stored: {processed}. Skipped: {skipped}.")
    finally:
        session.close()


if __name__ == "__main__":
    main()

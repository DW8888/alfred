import argparse
import json
from pathlib import Path
from typing import List

from dotenv import load_dotenv

import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.db.repo import SessionLocal  # noqa: E402
from backend.db.models import Job, GeneratedArtifact  # noqa: E402


def fetch_jobs_with_resumes(session) -> List[Job]:
    """Return jobs that already have at least one resume artifact."""
    return (
        session.query(Job)
        .join(
            GeneratedArtifact,
            (GeneratedArtifact.job_id == Job.id)
            & (GeneratedArtifact.artifact_type.like("resume%")),
        )
        .distinct()
        .order_by(Job.id.asc())
        .all()
    )


def main():
    parser = argparse.ArgumentParser(
        description="Build a queue JSON for every job that already has a resume artifact."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval/cover_letter_queue.json"),
        help="Path to write the queue JSON file.",
    )
    args = parser.parse_args()

    load_dotenv()

    session = SessionLocal()
    try:
        jobs = fetch_jobs_with_resumes(session)
    finally:
        session.close()

    queue = []
    for job in jobs:
        queue.append(
            {
                "job_id": job.id,
                "title": job.title or "",
                "company": job.company or "",
                "score": job.match_score,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        json.dump({"queue": queue}, fh, indent=2)

    print(f"Wrote {len(queue)} queue entries to {args.output}")


if __name__ == "__main__":
    main()

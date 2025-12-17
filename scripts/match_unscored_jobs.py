import argparse
import os
import sys
from pathlib import Path
from typing import List

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.db.repo import SessionLocal  # noqa: E402
from backend.db.models import Job  # noqa: E402


def fetch_unscored_jobs(limit: int | None = None) -> List[Job]:
    session = SessionLocal()
    try:
        query = session.query(Job).filter(Job.match_score.is_(None)).order_by(Job.id.asc())
        if limit:
            query = query.limit(limit)
        jobs = query.all()
        # detach objects to safely close session
        for job in jobs:
            session.expunge(job)
        return jobs
    finally:
        session.close()


def run_match(job: Job, api_base: str, top_k: int = 10) -> float | None:
    payload = {
        "job_id": job.id,
        "title": job.title or "",
        "company": job.company or "",
        "description": job.description or "",
        "top_k": top_k,
    }
    resp = requests.post(f"{api_base}/jobs/match", json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data.get("best_score")


def main():
    parser = argparse.ArgumentParser(
        description="Call /jobs/match for every DB job without match_score."
    )
    parser.add_argument(
        "--api-base",
        default=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"),
        help="Backend base URL (default: %(default)s or $API_BASE_URL)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on number of jobs to process",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Top K artifacts to request from /jobs/match",
    )
    args = parser.parse_args()

    load_dotenv()

    jobs = fetch_unscored_jobs(args.limit)
    if not jobs:
        print("No jobs with NULL match_score found.")
        return

    print(f"Processing {len(jobs)} jobs via {args.api_base}/jobs/match ...")
    successes = 0
    failures = 0

    for job in jobs:
        try:
            score = run_match(job, args.api_base.rstrip("/"), top_k=args.top_k)
            successes += 1
            print(f"[OK] Job {job.id} -> best_score={score}")
        except Exception as exc:
            failures += 1
            print(f"[ERR] Job {job.id} failed: {exc}")

    print(f"Completed. Successes: {successes}, Failures: {failures}")


if __name__ == "__main__":
    main()

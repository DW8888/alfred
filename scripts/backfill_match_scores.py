import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.db.repo import SessionLocal  # noqa: E402
from backend.db.models import Job  # noqa: E402


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"State file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def backfill_scores(state_file: Path, dry_run: bool = False) -> int:
    data = load_state(state_file)
    processed = data.get("processed_jobs", {})
    if not isinstance(processed, dict):
        raise ValueError("matcher_state.json missing 'processed_jobs' dict")

    updated = 0
    session = SessionLocal()

    try:
        for job_id_str, payload in processed.items():
            try:
                job_id = int(job_id_str)
            except (TypeError, ValueError):
                continue

            score = payload.get("score")
            if score is None:
                continue

            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                continue

            if job.match_score == score:
                continue

            job.match_score = score
            updated += 1

        if dry_run:
            session.rollback()
        else:
            session.commit()

        return updated
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Backfill job.match_score values from matcher_state.json"
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=Path("matcher_state.json"),
        help="Path to matcher_state.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute updates without writing to the database",
    )
    args = parser.parse_args()

    load_dotenv()
    updated = backfill_scores(args.state, args.dry_run)
    if args.dry_run:
        print(f"[dry-run] Would update match_score for {updated} jobs")
    else:
        print(f"Updated match_score for {updated} jobs")


if __name__ == "__main__":
    main()

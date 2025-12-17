import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, Set

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.db.repo import SessionLocal  # noqa: E402
from backend.db.models import Job  # noqa: E402


def fetch_unscored_job_ids() -> Set[int]:
    """Return the set of job IDs that do not have a match_score."""
    session = SessionLocal()
    try:
        rows = session.query(Job.id).filter(Job.match_score.is_(None)).all()
        return {row[0] for row in rows}
    finally:
        session.close()


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"State file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def prune_state(state: Dict[str, Any], job_ids: Set[int]) -> Dict[str, int]:
    """Remove the provided job IDs from processed/queued/skipped maps."""
    removed_counts = {"processed_jobs": 0, "queued_jobs": 0, "skipped_jobs": 0}
    target_ids = {str(job_id) for job_id in job_ids}

    for key in removed_counts.keys():
        mapping = state.get(key)
        if not isinstance(mapping, dict):
            continue

        for job_id in list(mapping.keys()):
            if job_id in target_ids:
                mapping.pop(job_id, None)
                removed_counts[key] += 1

    return removed_counts


def save_state(path: Path, state: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Remove jobs without match_score from matcher_state.json so the matcher will reprocess them."
        )
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
        help="Show what would be removed without touching the state file",
    )
    args = parser.parse_args()

    load_dotenv()

    job_ids = fetch_unscored_job_ids()
    if not job_ids:
        print("No jobs with NULL match_score found.")
        return

    state = load_state(args.state)
    removed_counts = prune_state(state, job_ids)

    total_removed = sum(removed_counts.values())
    print(
        f"Identified {len(job_ids)} jobs without match_score. "
        f"Would remove {removed_counts['processed_jobs']} processed, "
        f"{removed_counts['queued_jobs']} queued, "
        f"{removed_counts['skipped_jobs']} skipped entries."
    )

    if args.dry_run:
        print("[dry-run] State file left untouched.")
        return

    save_state(args.state, state)
    print(f"State file updated. Total entries removed: {total_removed}")


if __name__ == "__main__":
    main()

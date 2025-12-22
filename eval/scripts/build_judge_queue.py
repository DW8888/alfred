import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.db.repo import SessionLocal  # noqa: E402
from backend.db.models import GeneratedArtifact  # noqa: E402


def fetch_ordered_resume_ids(session):
    """Return all resume artifact IDs sorted ascending."""
    rows = (
        session.query(GeneratedArtifact.id)
        .filter(GeneratedArtifact.artifact_type.ilike("resume%"))
        .order_by(GeneratedArtifact.id.asc())
        .all()
    )
    return [row[0] for row in rows]


def main():
    parser = argparse.ArgumentParser(description="Build a processing queue of resume artifact IDs.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval/judge_queue.json"),
        help="Path to write the queue JSON file.",
    )
    args = parser.parse_args()

    load_dotenv()

    session = SessionLocal()
    try:
        artifact_ids = fetch_ordered_resume_ids(session)
    finally:
        session.close()

    payload = {"pending": artifact_ids}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    print(f"Wrote {len(artifact_ids)} artifact IDs to {args.output}")


if __name__ == "__main__":
    main()

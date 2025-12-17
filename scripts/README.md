# Scripts

One-off utilities for maintaining Alfred’s queues, database state, and evaluation artifacts. Run these from the repo root with the backend virtualenv when possible.

## Contents

- `backfill_match_scores.py` – iterates through `matcher_state.json` and writes stored scores back to `jobs.match_score`; handy if the matcher missed persisting scores. Supports a `--dry-run` mode so you can preview updates without touching the database.
- `embed_job_descriptions.py` – generates OpenAI embeddings for every job description and stores them in `jobs.description_embedding`; useful for analytics or future retrieval tasks. Accepts `--limit` and `--include-existing` to control batch size or force regeneration.
- `generate_resumes_for_ids.py` – calls the resume generation endpoint for a supplied list of job IDs, capturing output artifacts en masse. Ideal for rebuilding packages after major prompt/profile updates.
- `generate_resumes_with_job_focus.py` – similar to the previous script but targets the job-focused resume endpoint, emphasizing stated requirements in the final document. Lets you experiment with different prompt styles without touching the UI.
- `match_unscored_jobs.py` – fetches every database job missing `match_score` and replays `/jobs/match` so scores are populated retroactively. Helpful after bug fixes that previously skipped score persistence.
- `reset_unscored_jobs_state.py` – removes jobs without scores from `matcher_state.json` so the agent will reprocess them. Pair it with `match_unscored_jobs.py` when cleaning up stale runs.
- `__pycache__/` – Python bytecode cache (safe to ignore).

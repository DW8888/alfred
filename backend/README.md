# Backend

Python FastAPI + worker stack that powers Alfred’s APIs, agents, and persistence layers.

## Contents

- `agents/` – autonomous workers (job fetcher, matcher, resume agent) that orchestrate the workflow via background loops.
- `db/` – SQLAlchemy models, session helpers, and migrations/schema utilities.
- `generated/` – artifacts created at runtime (PDFs, text outputs) for auditing.
- `knowledge_base/` – ingestion helpers and source material for the artifact store.
- `profile/` – user profile JSON plus helpers for loading/saving immutable resume data.
- `queue/` – lightweight JSON queues used to pass work between agents.
- `rag/` – retrieval-augmented generation utilities and experiments.
- `routes/` – FastAPI routers for jobs, resumes, and debugging endpoints.
- `tests/` – unit/integration tests for backend modules.
- `utils/` – shared helper modules (embedding, text cleanup, skill extraction, etc.).
- `venv/` – local Python virtual environment (excluded from version control in production).
- `__pycache__/` – interpreter cache files.
- `main.py` – FastAPI app entrypoint; wires routers, middleware, and database setup so the backend can run under Uvicorn/Gunicorn.
- `requirements.txt` – pinned Python dependencies for reproducible installs.
- `__init__.py` – marks the backend directory as a Python package for relative imports.

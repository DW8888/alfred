# Alfred: The Agentic Job Assistant

Alfred automates job discovery, matching, and document generation by combining FastAPI agents with Retrieval-Augmented Generation (RAG). Everything runs locally today, but the repo is structured for AWS deployment once the workflow is stable.

## Current Status (December 2025)
- **Backend** � FastAPI API plus background agents (fetcher, matcher, resume agent) are stable. They support job ingestion, hybrid matching, resume/cover generation, and JSON queue/state management.
- **Frontend** � Next.js dashboard is live. It lets you configure the API endpoint, edit profile data, trigger fetch/match flows, and view console output (now pinned on the right side).
- **Database** � PostgreSQL + pgvector stores artifacts, jobs, and generated documents. Job descriptions now have cached embeddings (jobs.description_embedding).
- **Infrastructure** � Local docker-compose + AWS scaffolding exist, though deployment automation is still in progress.

## Repository Layout
`
alfred/
+-- backend/          # FastAPI services, agents, DB models
+-- frontend/         # Next.js control panel
+-- scripts/          # Maintenance + evaluation helpers
+-- docs/             # Architecture notes
+-- eval/             # Resume/reasoning artifacts
+-- infrastructure/   # Local + AWS deployment assets
+-- model/            # LLM experimentation harnesses
+-- FinalProject/     # Presentation + references
+-- README.md
`

## Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 15+ with the ector extension
- OpenAI API key (plus any optional provider keys referenced in .env)

## Backend Setup
1. cd backend
2. python -m venv venv
3. Activate: source venv/bin/activate (PowerShell: env\Scripts\Activate.ps1)
4. pip install -r requirements.txt
5. Copy .env.example to .env in repo root; set DATABASE_URL, OPENAI_API_KEY, and other creds.
6. In Postgres, run CREATE EXTENSION IF NOT EXISTS vector;
7. Initialize tables (python -m backend.db.repo or run migrations).
8. Launch API: uvicorn backend.main:app --reload
9. Run agents as needed (each in its own shell):
   - python backend/agents/job_fetcher.py
   - python backend/agents/job_matcher.py
   - python backend/agents/resume_agent.py
10. Maintenance utilities (from repo root):
    - python scripts/reset_unscored_jobs_state.py � requeue jobs missing match_score
    - python scripts/match_unscored_jobs.py � re-run /jobs/match to backfill database scores
    - python scripts/embed_job_descriptions.py � cache embeddings into jobs.description_embedding

### Running Postgres via Docker
1. Install Docker Desktop (or another OCI-compatible runtime).
2. From repo root, start the compose service:
   `ash
   docker compose -f infrastructure/docker-compose.yml up -d postgres
   `
3. Verify the container is healthy with docker ps (service name defaults to lfred-postgres).
4. Ensure your .env DATABASE_URL points to this instance (default: postgresql+psycopg2://alfred:alfred123@localhost:5432/alfred_db).
5. When finished, shut it down via docker compose -f infrastructure/docker-compose.yml down.

## Frontend Setup
1. cd frontend
2. 
pm install
3. Create .env.local (e.g., NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000)
4. 
pm run dev
5. Open http://localhost:3000
6. Use the *API Endpoint* card to point at your backend, then drive the workflow (fetch jobs, view matches, generate docs).

## Database Notes
- Example connection string (in .env): 
- Useful queries:
  - Count unmatched jobs: SELECT COUNT(*) FROM jobs WHERE match_score IS NULL;
  - Count missing embeddings: SELECT COUNT(*) FROM jobs WHERE description_embedding IS NULL;
- Key tables:
  - jobs > job postings, match scores, embeddings
  - artifacts > user resumes/snippets with embeddings
  - generated_artifacts > persisted resumes/cover letters for auditability

## Testing
- Backend: pytest backend/tests
- Frontend: 
pm run lint and (if configured) 
pm run test
- Scripts: run individually with the backend virtualenv active

## Deployment Roadmap
- Containerize backend/frontend, push to ECR (or similar) and deploy via ECS/Fargate or Amplify
- Use managed Postgres (RDS) with pgvector
- Schedule agents via ECS services, Batch, or Lambda cron
- Wire CI/CD through GitHub Actions for lint/test/build/deploy

## Contributing
1. Branch from dev
2. Implement changes + add tests
3. Run lint/tests
4. Submit PR targeting dev

For questions, open an issue or contact Darwhin Gomez.

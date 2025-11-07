# Alfred System Design

## 1. Purpose and Goal
Alfred is a personal, agentic job assistant designed to automate job discovery, ranking, and application tailoring.  
The goal is to use Retrieval-Augmented Generation (RAG) with your prior resumes, GitHub projects, and writing samples to create grounded, contextually accurate job applications, generate accurate and specific resumes and cover letters, and track applications end-to-end.

### Primary Objectives
- Parse and structure job postings from multiple sources.  
- Evaluate each job’s alignment with your skills.  
- Generate resume and cover letter variants backed by real evidence from your portfolio.  
- Track job applications and maintain their status.  
- Optionally assist in form-filling for applications (with human approval).

---

## 2. Major Components

| Component | Role |
|------------|------|
| **Frontend (Next.js)** | User interface for tracking jobs, reviewing generated documents, and approving applications. |
| **Backend API (FastAPI)** | Core orchestration layer handling requests from the frontend and managing the agent workflow. |
| **Database (PostgreSQL + pgvector)** | Stores job records, artifacts (resumes/projects), embeddings for RAG retrieval, and application status data. |
| **Agents** | Independent modules that perform specific functions: watcher, parser, ranker, tailor, apply. |
| **RAG Engine** | Handles embedding generation, similarity search, and context retrieval from your personal knowledge base. |
| **LLM Layer (OpenAI API)** | Used for natural language understanding (job parsing) and generation (resume/cover letter tailoring). |
| **File Storage (local → S3)** | Stores raw job descriptions, generated resume files, and cover letters. |
| **Scheduler/Workflow Orchestrator** | Manages periodic scans, processing queues, and retries (EventBridge or Celery). |

---

## 3. Data Flow

1. **Watcher Agent**  
   - Monitors selected job sources (LinkedIn, Greenhouse, etc.) or accepts manual input.  
   - Stores raw job descriptions in the database.  

2. **Parser Agent**  
   - Cleans the text and extracts structure (title, company, skills, requirements).  
   - Saves a standardized JSON version to the database.  

3. **Ranker Agent**  
   - Retrieves relevant information from your artifact corpus using embedding similarity (pgvector).  
   - Calculates a match score and identifies skill gaps.  

4. **Tailor Agent**  
   - Uses the OpenAI API to generate customized resumes and cover letters based on the job’s extracted details and retrieved context.  
   - Stores outputs as files in local storage (later S3).  

5. **Apply Agent**  
   - Prefills job applications (where permitted) and pauses for human approval before submission.  
   - Updates application tracking data in the database.  

6. **Frontend Dashboard**  
   - Displays job list, scores, documents, and action buttons for review and approval.  
   - Shows the current status of each application.  

---

## 4. Technology Stack Summary

| Layer | Tool |
|--------|------|
| **Backend Framework** | FastAPI |
| **Database** | PostgreSQL + pgvector |
| **Embedding Model** | OpenAI embeddings |
| **LLM Model** | OpenAI GPT-4o |
| **Frontend** | Next.js |
| **Storage** | Local (dev), AWS S3 (prod) |
| **Deployment** | AWS Amplify (frontend), App Runner or ECS (backend), RDS (database) |
| **Authentication** | AWS Cognito (future addition) |

---

## 5. Deployment Overview

### Local (development phase)
- Run PostgreSQL in Docker with pgvector enabled.  
- FastAPI server runs locally on port 8000.  
- Next.js dashboard runs locally on port 3000.  
- All API keys stored in `.env`.  

### AWS (production phase)
- Backend containerized and deployed via App Runner or ECS.  
- PostgreSQL → RDS with pgvector extension.  
- S3 used for file persistence.  
- Amplify hosts the Next.js frontend.  
- Cognito handles authentication.  
- EventBridge triggers periodic watchers and agents.  

---

## 6. Scalability and Security

- **Scaling**: Each agent is modular; they can run as separate Lambda functions or containers if needed.  
- **RAG size**: PostgreSQL with pgvector scales well for small to medium embeddings (~100k vectors). For larger datasets, migrate to OpenSearch vector store.  
- **Secrets management**: Use `.env` locally and AWS Secrets Manager in production.  
- **Network**: Private subnets for backend and DB (VPC setup in AWS).  
- **Access control**: Frontend authenticated via Cognito tokens; all user data scoped to a single account.  
- **Audit trail**: All generated artifacts logged with timestamps, version references, and application tracking details.
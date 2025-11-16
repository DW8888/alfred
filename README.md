# Alfred: The Agentic Job Assistant

Alfred is a personal project developed by Darwhin Gomez.
It is an agentic system that automates job tracking, ranking, and resume tailoring using Retrieval-Augmented Generation (RAG).
The project runs locally first, then will be deployed to AWS.
alfred/
├── backend/ # FastAPI backend & RAG pipeline
├── frontend/ # Next.js dashboard (planned)
├── infrastructure/ # Local/AWS deployment
└── docs/ # Notes and documentation


## Planned Stack
- Backend: FastAPI + SQLAlchemy  
- Database: PostgreSQL + pgvector  
- LLM: OpenAI GPT-4o  
- Frontend: Next.js  
- Deployment: AWS (Amplify, RDS, S3)
- CI-CD GitHub
- Docker
================================================================
## Setup
```bash
git clone https://github.com/<dw8888>/alfred.git
cd alfred/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload

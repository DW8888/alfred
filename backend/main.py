from fastapi import FastAPI
from sqlalchemy import create_engine, text,TIMESTAMP
from dotenv import load_dotenv

from backend.db.repo import init_db
from backend.routes import jobs, search, artifacts, github_generate
import os

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Initialize DB engine
engine = create_engine(DATABASE_URL, echo=False, future=True)

app = FastAPI(title="Alfred Backend")
@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(jobs.router)
app.include_router(search.router)
app.include_router(artifacts.router, prefix="/artifacts")
app.include_router(github_generate.router)
@app.get("/health")
def health_check():
    """Verify API and database connectivity"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 'ok' AS status")).fetchone()
            return {"database": result.status, "api": "running"}
    except Exception as e:
        return {"database": f"error: {e}", "api": "running"}



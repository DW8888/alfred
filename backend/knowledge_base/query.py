from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.db.repo import SessionLocal
from backend.db.models import Artifact
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def retrieve_context(job_description: str, k: int = 3):
    db: Session = SessionLocal()
    embedding = client.embeddings.create(
        model="text-embedding-3-small",
        input=job_description
    ).data[0].embedding

    results = db.execute(text("""
        SELECT name, content, source, embedding <-> :embed AS distance
        FROM artifacts
        ORDER BY embedding <-> :embed
        LIMIT :k
    """), {"embed": embedding, "k": k}).fetchall()

    db.close()
    return results

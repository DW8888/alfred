from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.db.repo import SessionLocal
from openai import OpenAI
import os

router = APIRouter(prefix="/search", tags=["Search"])

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Request schema
class SearchRequest(BaseModel):
    query: str
    top_k: int = 3  # how many results to return

# Response schema
class SearchResult(BaseModel):
    name: str
    source: str
    similarity: float
    snippet: str

@router.post("/", response_model=list[SearchResult])
def search_artifacts(request: SearchRequest):
    db: Session = SessionLocal()

    try:
        # Step 1: Embed the query
        embedding = client.embeddings.create(
            model="text-embedding-3-small",
            input=request.query
        ).data[0].embedding

        # Step 2: Run vector similarity search using pgvector
        sql = text("""
            SELECT name, source, content,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM artifacts
            ORDER BY similarity DESC
            LIMIT :top_k;
        """)

        results = db.execute(sql, {"embedding": embedding, "top_k": request.top_k}).fetchall()

        # Step 3: Format output
        return [
            SearchResult(
                name=row.name,
                source=row.source,
                similarity=float(row.similarity),
                snippet=row.content[:250]
            )
            for row in results
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        db.close()

# backend/utils/embedding.py

from typing import List, Tuple,Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ---------------------------------------------------------
# 1. Embed text using OpenAI "text-embedding-3-small"
#    Returns a Python list[float] that can be cast to pgvector
# ---------------------------------------------------------
def embed_text(text: str) -> List[float]:
    """
    Generate an embedding for text using OpenAI.
    Output is a simple Python list[float] compatible with pgvector.
    """

    if not text.strip():
        return [0.0] * 1536

    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )

    return resp.data[0].embedding


# ---------------------------------------------------------
# 2. Search similar artifacts using pgvector
#    Returns list of (ArtifactModel, similarity_score)
# ---------------------------------------------------------
def search_similar_artifacts(
    db: Session,
    embedding: List[float],
    top_k: int = 5
) -> List[Tuple[Any, float]]:
    """
    Perform pgvector similarity search against artifacts table.

    Returns:
        [
           (ArtifactModel, similarity_float),
           ...
        ]
    """

    # pgvector similarity:
    #     cosine_similarity = 1 - (embedding <=> artifact.embedding)
    sql = text("""
        SELECT id,
               name,
               content,
               source,
               1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM artifacts
        ORDER BY similarity DESC
        LIMIT :top_k;
    """)

    rows = db.execute(sql, {
        "embedding": embedding,
        "top_k": top_k
    }).fetchall()

    if not rows:
        return []

    # Load Artifact model (ORM) for each row
    from backend.db.models import Artifact

    results = []
    for r in rows:
        art = db.query(Artifact).filter(Artifact.id == r.id).first()
        if art:
            results.append((art, float(r.similarity)))

    return results

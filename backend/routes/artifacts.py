from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.db.repo import get_db
from backend.db.models import Artifact
from backend.utils.text_cleaner import clean_text
from openai import OpenAI
import os

router = APIRouter()

@router.post("/ingest_raw")
def ingest_raw_artifact(payload: dict, db: Session = Depends(get_db)):
    name = payload.get("name")
    content = payload.get("content")
    source = payload.get("source", "manual")
    metadata = payload.get("metadata", {})

    if not name or not content:
        raise HTTPException(status_code=400, detail="Missing required fields")

    cleaned = clean_text(content)

    # Embed text
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    embedding = client.embeddings.create(
        model="text-embedding-3-small",
        input=cleaned
    ).data[0].embedding

    record = Artifact(
        name=name,
        content=cleaned,
        embedding=embedding,
        source=source,
        artifact_metadata=metadata   # <— CORRECT FIELD
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return {"id": record.id, "name": name}

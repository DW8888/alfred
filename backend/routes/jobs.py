from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.db.models import Job
from backend.db.repo import SessionLocal
from backend.db.schemas import JobCreate, JobRead
from backend.utils.text_cleaner import clean_text  #  Added import
from typing import List
from openai import OpenAI
from pydantic import BaseModel
import os

router = APIRouter(prefix="/jobs", tags=["Jobs"])

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --------------------------------------------------------------------
# Database dependency
# --------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --------------------------------------------------------------------
# CRUD endpoints
# --------------------------------------------------------------------
@router.post("/", response_model=JobRead)
def create_job(job: JobCreate, db: Session = Depends(get_db)):
    new_job = Job(**job.dict())
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job

@router.get("/", response_model=List[JobRead])
def get_jobs(db: Session = Depends(get_db)):
    return db.query(Job).all()

# --------------------------------------------------------------------
# Job matching endpoint
# --------------------------------------------------------------------
class JobMatchRequest(BaseModel):
    job_title: str
    company: str | None = None
    description: str
    top_k: int = 3

class JobMatchResult(BaseModel):
    name: str
    similarity: float
    snippet: str

@router.post("/match", response_model=dict)
def match_job(request: JobMatchRequest, db: Session = Depends(get_db)):
    """Compare a job description against stored artifacts using embeddings."""
    try:
        # ✅ Clean all incoming text
        title = clean_text(request.job_title)
        company = clean_text(request.company or "")
        description = clean_text(request.description)
        job_text = f"{title}\n{company}\n{description}"

        # 1. Embed job description
        embedding = client.embeddings.create(
            model="text-embedding-3-small",
            input=job_text
        ).data[0].embedding

        # 2. Query artifacts table via cosine similarity
        sql = text("""
            SELECT name, content,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM artifacts
            ORDER BY similarity DESC
            LIMIT :top_k;
        """)
        results = db.execute(sql, {"embedding": embedding, "top_k": request.top_k}).fetchall()

        # 3. Format output
        matches = [
            JobMatchResult(
                name=row.name,
                similarity=float(row.similarity),
                snippet=row.content[:300]
            )
            for row in results
        ]

        return {
            "job_title": title,
            "company": company,
            "matches": matches
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --------------------------------------------------------------------
# Resume Generation Endpoint
# --------------------------------------------------------------------
@router.post("/generate_resume", response_model=dict)
def generate_resume(request: JobMatchRequest, db: Session = Depends(get_db)):
    """
    Generate a factual resume tailored to a job description,
    using only verified content from existing artifacts.
    """
    try:
        # ✅ Clean inputs first
        title = clean_text(request.job_title)
        company = clean_text(request.company or "")
        description = clean_text(request.description)
        job_text = f"{title}\n{company}\n{description}"

        # 1. Embed the job description
        embedding = client.embeddings.create(
            model="text-embedding-3-small",
            input=job_text
        ).data[0].embedding

        # 2. Retrieve top-matching artifacts (reuse RAG retrieval)
        sql = text("""
            SELECT name, content,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM artifacts
            ORDER BY similarity DESC
            LIMIT :top_k;
        """)
        results = db.execute(sql, {"embedding": embedding, "top_k": request.top_k}).fetchall()

        # 3. Combine retrieved content
        context = "\n\n---\n\n".join([r.content for r in results])

        # 4. Use GPT-4o-mini to summarize into a grounded resume
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional resume generator. "
                        "Only use the text provided in the context below. "
                        "Do not add or invent new skills, experiences, or dates. "
                        "Reorganize, format, and polish the information into a clean, factual resume "
                        "tailored for the provided job description. "
                        "No emojis or icons. Keep it clean, professional, and within one page."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Job Description:\n{job_text}\n\nContext from my artifacts:\n{context}",
                },
            ],
            temperature=0.2,  # factual and consistent
        )

        resume_text = completion.choices[0].message.content.strip()

        return {
            "job_title": title,
            "company": company,
            "generated_resume": resume_text
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --------------------------------------------------------------------
# Cover Letter Generation Endpoint
# --------------------------------------------------------------------
@router.post("/generate_cover_letter", response_model=dict)
def generate_cover_letter(request: JobMatchRequest, db: Session = Depends(get_db)):
    """
    Generate a factual, concise cover letter tailored to the job description.
    Uses only verified content from your stored artifacts.
    """
    try:
        # ✅ Clean inputs immediately
        title = clean_text(request.job_title)
        company = clean_text(request.company or "")
        description = clean_text(request.description)
        job_text = f"{title}\n{company}\n{description}"

        # 1. Embed the job description
        embedding = client.embeddings.create(
            model="text-embedding-3-small",
            input=job_text
        ).data[0].embedding

        # 2. Retrieve top relevant artifacts from DB
        sql = text("""
            SELECT name, content,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM artifacts
            ORDER BY similarity DESC
            LIMIT :top_k;
        """)
        results = db.execute(sql, {"embedding": embedding, "top_k": request.top_k}).fetchall()

        # 3. Combine verified context
        context = "\n\n---\n\n".join([r.content for r in results])

        # 4. Generate cover letter via GPT-4o-mini
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an assistant that writes concise, professional cover letters. "
                        "Only use verified information from the context. "
                        "Do not fabricate or assume new details. "
                        "Maintain a professional tone and standard structure (intro, skills alignment, interest, closing). "
                        "Limit the letter to one page."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Job Description:\n{job_text}\n\n"
                        f"My verified background and experience:\n{context}\n\n"
                        "Generate a factual one-page cover letter aligned to this job."
                    ),
                },
            ],
            temperature=0.3,
        )

        letter_text = completion.choices[0].message.content.strip()

        return {
            "job_title": title,
            "company": company,
            "generated_cover_letter": letter_text
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

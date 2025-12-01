# backend/routes/jobs.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

import os
import json
from typing import List, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

from backend.db.models import Job
from backend.db.repo import SessionLocal
from backend.db.schemas import JobCreate, JobRead

from backend.utils.text_cleaner import clean_text
from backend.utils.embedding import embed_text, search_similar_artifacts
from backend.utils.skills_extractor_llm import extract_skills_llm

from pydantic import BaseModel

load_dotenv()

router = APIRouter(prefix="/jobs", tags=["Jobs"])

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# --------------------------------------------------------------------
# Database Dependency
# --------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------
# CRUD: Create Job
# --------------------------------------------------------------------
@router.post("/", response_model=JobRead)
def create_job(job: JobCreate, db: Session = Depends(get_db)):

    db_job = Job(**job.dict())

    try:
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        return db_job

    except IntegrityError:
        db.rollback()
        existing = db.query(Job).filter(Job.source_url == job.source_url).first()
        return existing


# --------------------------------------------------------------------
# CRUD: List Jobs
# --------------------------------------------------------------------
@router.get("/", response_model=List[JobRead])
def get_jobs(db: Session = Depends(get_db)):
    return db.query(Job).all()


# --------------------------------------------------------------------
# CRUD: Get Single Job
# --------------------------------------------------------------------
@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# --------------------------------------------------------------------
# Job Match Request Model
# --------------------------------------------------------------------
class JobMatchRequest(BaseModel):
    title: str
    company: str | None = None
    description: str
    top_k: int = 4


# --------------------------------------------------------------------
# Helper: Convert skill dict → skill set safely
# --------------------------------------------------------------------
def _skills_to_set(sk: Dict[str, List[str]]) -> set:
    """
    Job/artifact skills are dicts like:
      {
        "languages": [...],
        ...,
        "all": [...]
      }
    We'll primarily rely on "all", but fall back to union of categories.
    """
    if not sk:
        return set()

    all_list = sk.get("all", [])
    if all_list:
        return {s.strip().lower() for s in all_list if str(s).strip()}

    agg = set()
    for k, vals in sk.items():
        if k == "all":
            continue
        for v in vals or []:
            v = str(v).strip().lower()
            if v:
                agg.add(v)
    return agg


# --------------------------------------------------------------------
# Hybrid Job Matcher (Semantic + LLM Skill Overlap)
# --------------------------------------------------------------------
@router.post("/match")
def match_job(req: JobMatchRequest) -> Dict[str, Any]:
    """
    Hybrid job matcher:
      - Semantic similarity (pgvector)
      - LLM-extracted skill overlap (GPT-4o-mini)
      - Combined hybrid score = 0.6*semantic + 0.4*skill
    """

    if not req.description.strip():
        raise HTTPException(status_code=400, detail="Job description is required")

    full_text = f"{req.title}\n{req.company or ''}\n{req.description}"

    # 1. Encode job posting into vector
    query_vec = embed_text(full_text)

    # 2. Retrieve relevant artifacts
    db = SessionLocal()
    try:
        matches_raw = search_similar_artifacts(db, query_vec, top_k=req.top_k)
    finally:
        db.close()

    # 3. Extract job skills via LLM
    job_sk = extract_skills_llm(full_text)
    job_set = _skills_to_set(job_sk)

    print("\n================ DEBUG: LLM EXTRACTED JOB SKILLS ================\n")
    print(json.dumps(job_sk, indent=2))
    print("=================================================================\n")

    enriched_matches = []

    for art, sim in matches_raw:
        art_content = art.content or ""

        # 4. Extract artifact skills via LLM
        art_sk = extract_skills_llm(art_content)
        art_set = _skills_to_set(art_sk)

        print("\n================ DEBUG: RAW LLM ARTIFACT SKILLS ================\n")
        print(json.dumps(art_sk, indent=2))
        print("=================================================================\n")

        # 5. Compute skill overlap using precision on job skills
        if job_set:
            inter = job_set & art_set
            sk_overlap = len(inter) / len(job_set)
        else:
            inter = set()
            sk_overlap = 0.0

        union = job_set | art_set  # for debug printing only


        # 6. Hybrid score (semantic + bonus from skills)
        semantic = float(sim)
        skill = float(sk_overlap)
        combined = semantic + 0.3 * skill
        if combined > 1.0:
            combined = 1.0

        snippet = (
            art_content[:400] + "..."
            if len(art_content) > 400
            else art_content
        )

        # Verbose skill debug
        print("\n================ SKILL DEBUG ================\n")
        print(f"Artifact: {art.name}")
        print(f"Similarity: {semantic:.4f}")
        print(f"Job Skills: {job_set}")
        print(f"Artifact Skills: {art_set}")
        print(f"Intersection: {inter}")
        print(f"Union: {union}")
        print(f"Skill Overlap Score: {sk_overlap:.4f}")
        print(f"Combined Score: {combined:.4f}")
        print("=============================================\n")

        enriched_matches.append({
            "artifact_id": art.id,
            "name": art.name,
            "similarity": semantic,
            "skill_overlap": float(sk_overlap),
            "combined_score": float(combined),
            "snippet": snippet,
            "source": art.source,
        })

    enriched_matches.sort(key=lambda m: m["combined_score"], reverse=True)

    return {
        "job_title": req.title,
        "company": req.company,
        "matches": enriched_matches,
    }


# --------------------------------------------------------------------
# Resume Generation Endpoint
# --------------------------------------------------------------------
@router.post("/generate_resume", response_model=dict)
def generate_resume(request: JobMatchRequest, db: Session = Depends(get_db)):

    try:
        title = clean_text(request.title)
        company = clean_text(request.company or "")
        description = clean_text(request.description)
        job_text = f"{title}\n{company}\n{description}"

        # 1. Embed job description
        embedding = client.embeddings.create(
            model="text-embedding-3-small",
            input=job_text
        ).data[0].embedding

        # 2. Retrieve top-matching artifacts
        sql = text("""
            SELECT name, content,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM artifacts
            ORDER BY similarity DESC
            LIMIT :top_k;
        """)

        rows = db.execute(sql, {"embedding": embedding, "top_k": request.top_k}).fetchall()

        # 3. Combine content
        context = "\n\n---\n\n".join([row.content for row in rows])

        # 4. Generate resume with GPT-4o-mini
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional resume generator. "
                        "Only use verified context. "
                        "Do NOT invent details. "
                        "Produce a clean, factual, 1-page resume."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Job Description:\n{job_text}\n\n"
                        f"Verified Context:\n{context}"
                    ),
                },
            ],
            temperature=0.2,
        )

        output = completion.choices[0].message.content.strip()

        return {
            "job_title": title,
            "company": company,
            "generated_resume": output
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------------------------
# Cover Letter Endpoint
# --------------------------------------------------------------------
@router.post("/generate_cover_letter", response_model=dict)
def generate_cover_letter(request: JobMatchRequest, db: Session = Depends(get_db)):

    try:
        title = clean_text(request.title)
        company = clean_text(request.company or "")
        description = clean_text(request.description)
        job_text = f"{title}\n{company}\n{description}"

        embedding = client.embeddings.create(
            model="text-embedding-3-small",
            input=job_text
        ).data[0].embedding

        sql = text("""
            SELECT name, content,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM artifacts
            ORDER BY similarity DESC
            LIMIT :top_k;
        """)

        rows = db.execute(sql, {"embedding": embedding, "top_k": request.top_k}).fetchall()
        context = "\n\n---\n\n".join([row.content for row in rows])

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write concise, professional cover letters. "
                        "Only use verified context. "
                        "Do not invent details. "
                        "1 page max."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Job Description:\n{job_text}\n\n"
                        f"My Verified Experience:\n{context}\n\n"
                        "Write a tailored cover letter."
                    ),
                },
            ],
            temperature=0.3,
        )

        output = completion.choices[0].message.content.strip()

        return {
            "job_title": title,
            "company": company,
            "generated_cover_letter": output
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

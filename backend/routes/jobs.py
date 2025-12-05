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
from backend.profile.utils import load_profile
from backend.agents.base import AgentConfig
from backend.agents.job_fetcher import JobFetcherAgent

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


def _build_context(rows: List[Any]) -> tuple[str, str]:
    profile = load_profile()
    profile_context = json.dumps(profile, indent=2)
    artifact_chunks = [row.content for row in rows if row.content]
    artifact_context = "\n\n---\n\n".join(artifact_chunks) if artifact_chunks else "None"
    combined = (
        "Structured Profile:\n"
        f"{profile_context}\n\n"
        "Artifacts:\n"
        f"{artifact_context}"
    )
    personal_info = profile.get("personal_info", {})
    contact = (
        "Use the following contact information exactly as provided. "
        f"Name: {personal_info.get('name', '')}. "
        f"Location: {personal_info.get('location', '')}. "
        f"Email: {personal_info.get('email', '')}. "
        f"Phone: {personal_info.get('phone', '')}. "
        f"Links: {personal_info.get('links', [])}."
    )
    return combined, contact


def _summarize_job_skills(skill_dict: Dict[str, List[str]]) -> str:
    skills = []
    for vals in skill_dict.values():
        if not vals:
            continue
        skills.extend(vals)
    unique = sorted({s.strip() for s in skills if str(s).strip()})
    return ", ".join(unique) if unique else "Not specified"


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

    # print("\n================ DEBUG: LLM EXTRACTED JOB SKILLS ================\n")
    # print(json.dumps(job_sk, indent=2))
    # print("=================================================================\n")

    enriched_matches = []

    for art, sim in matches_raw:
        art_content = art.content or ""

        # 4. Extract artifact skills via LLM
        art_sk = extract_skills_llm(art_content)
        art_set = _skills_to_set(art_sk)

        # print("\n================ DEBUG: RAW LLM ARTIFACT SKILLS ================\n")
        # print(json.dumps(art_sk, indent=2))
        # print("=================================================================\n")

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
        # print("\n================ SKILL DEBUG ================\n")
        # print(f"Artifact: {art.name}")
        # print(f"Similarity: {semantic:.4f}")
        # print(f"Job Skills: {job_set}")
        # print(f"Artifact Skills: {art_set}")
        # print(f"Intersection: {inter}")
        # print(f"Union: {union}")
        # print(f"Skill Overlap Score: {sk_overlap:.4f}")
        # print(f"Combined Score: {combined:.4f}")
        # print("=============================================\n")

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

        # 3. Combine structured profile + artifact context
        combined_context, contact_instructions = _build_context(rows)

        # 4. Generate reasoning + structured resume with GPT-4o-mini
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional resume generator. "
                        "Step 1: Analyze the job description and verified context to decide "
                        "if the candidate is a high match. Provide reasoning that cites concrete "
                        "facts from the verified context (reference technologies, achievements, "
                        "and employers). If information is missing, explicitly call it out. "
                        "Step 2: Produce a structured resume in Markdown with the sections "
                        "Header (name + contact), Summary, Core Competencies, Professional Experience, "
                        "Projects (optional), Education, Certifications, and Additional Information. "
                        "Only include details that are present in the verified context. "
                        "Never fabricate accomplishments or dates. "
                        f"{contact_instructions}"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Job Description:\n{job_text}\n\n"
                        f"Verified Context:\n{combined_context}\n\n"
                        "Return JSON with keys:\n"
                        "reasoning: short paragraph explaining why the match is strong (or weak), "
                        "citing evidence from Verified Context.\n"
                        "resume_markdown: the final structured resume in Markdown."
                    ),
                },
            ],
            temperature=0.2,
        )

        content = completion.choices[0].message.content
        try:
            parsed = json.loads(content)
        except Exception:
            parsed = {"reasoning": "", "resume_markdown": content.strip()}

        reasoning = parsed.get("reasoning", "").strip()
        resume_md = parsed.get("resume_markdown") or parsed.get("resume") or parsed.get("resume_text") or ""
        resume_md = (resume_md or "").strip()

        return {
            "job_title": title,
            "company": company,
            "reasoning": reasoning,
            "generated_resume": resume_md
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------------------------
# Job-Focused Resume Endpoint
# --------------------------------------------------------------------
@router.post("/generate_resume_job_focus", response_model=dict)
def generate_resume_job_focus(request: JobMatchRequest, db: Session = Depends(get_db)):
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
        combined_context, contact_instructions = _build_context(rows)

        job_skills = extract_skills_llm(job_text)
        job_skills_text = _summarize_job_skills(job_skills)

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional resume generator. "
                        "Analyze the job description and highlight the job's stated skills and responsibilities, "
                        "citing evidence from the verified context. "
                        "Produce a structured resume in Markdown with sections Header (name + contact), Summary, "
                        "Job Fit Highlights, Core Competencies, Professional Experience, Projects, Education, "
                        "Certifications, Additional Information. "
                        "Only include verifiable facts. "
                        f"{contact_instructions}"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Job Description:\n{job_text}\n\n"
                        f"Key Job Skills/Responsibilities:\n{job_skills_text}\n\n"
                        f"Verified Context:\n{combined_context}\n\n"
                        "Return JSON with keys:\n"
                        "reasoning: explain how the candidate matches the job requirements.\n"
                        "resume_markdown: the structured resume."
                    ),
                },
            ],
            temperature=0.2,
        )

        content = completion.choices[0].message.content
        try:
            parsed = json.loads(content)
        except Exception:
            parsed = {"reasoning": "", "resume_markdown": content.strip()}

        reasoning = parsed.get("reasoning", "").strip()
        resume_md = parsed.get("resume_markdown") or parsed.get("resume") or parsed.get("resume_text") or ""
        resume_md = (resume_md or "").strip()

        return {
            "job_title": title,
            "company": company,
            "reasoning": reasoning,
            "generated_resume": resume_md
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fetch_jobs")
def fetch_jobs():
    backend_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    config = AgentConfig(
        backend_url=backend_url,
        state_path="fetcher_state.json",
        sleep_interval=0,
    )
    agent = JobFetcherAgent(config)
    agent.step()
    return {"status": "ok", "message": "Job fetcher completed one cycle."}


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

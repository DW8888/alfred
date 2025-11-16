import os
import re
from typing import Dict, Any, Optional

from .base import BaseAgent, AgentConfig
from backend.utils.pdf_writer import write_pdf
from backend.db.repo import SessionLocal
from backend.db.models import ApplicationPackage


# -------------------------
# Filename Sanitizer
# -------------------------
def safe_filename(text: str) -> str:
    text = text.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_]+", "", text)


# -------------------------
# Output Directories
# -------------------------
BASE_DIR = "backend/generated"
RESUME_DIR = os.path.join(BASE_DIR, "resumes")

os.makedirs(RESUME_DIR, exist_ok=True)


class ResumeAgent(BaseAgent):
    """
    Generates ONLY resumes for strong matched jobs.

    Workflow:
      1. Pop a strong match
      2. Fetch job details
      3. Call /jobs/generate_resume
      4. Save PDF
      5. Insert into DB
      6. Mark job complete
    """

    def __init__(self, config: AgentConfig):
        super().__init__("ResumeAgent", config)

        if "completed_resumes" not in self.state:
            self.state["completed_resumes"] = {}

    # -------------------------
    # Backend Helpers
    # -------------------------
    def fetch_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        return self.api_get(f"/jobs/{job_id}")

    def generate_resume(self, title: str, company: str, description: str) -> Optional[str]:
        payload = {
            "title": title,
            "company": company,
            "description": description,
            "top_k": 5
        }
        resp = self.api_post("/jobs/generate_resume", payload)
        if not resp:
            return None
        return resp.get("generated_resume")

    # -------------------------
    # State Helpers
    # -------------------------
    def get_next_match(self):
        matches = self.state.get("strong_matches", [])
        if matches:
            return matches.pop(0)
        return None

    def is_completed(self, job_id: int) -> bool:
        return str(job_id) in self.state["completed_resumes"]

    # -------------------------
    # Main Step()
    # -------------------------
    def step(self):

        self.logger.info("ResumeAgent: checking for strong matches...")

        match = self.get_next_match()
        if not match:
            self.logger.info("ResumeAgent: no matches pending.")
            return

        job_id = match["job_id"]
        score = match["score"]

        if self.is_completed(job_id):
            self.logger.info(f"ResumeAgent: job {job_id} already processed.")
            return

        job = self.fetch_job(job_id)
        if not job:
            self.logger.error(f"ResumeAgent: failed to fetch job {job_id}")
            return

        title = job.get("title", "")
        company = job.get("company", "")
        description = job.get("description", "")

        # -------------------------
        # Generate Resume Text
        # -------------------------
        resume_text = self.generate_resume(title, company, description)
        if resume_text is None:
            self.logger.error(f"ResumeAgent: resume generation failed for job {job_id}")
            return

        # -------------------------
        # Build filename
        # -------------------------
        prefix = f"{job_id}_{safe_filename(company)}_{safe_filename(title)}"
        pdf_path = os.path.join(RESUME_DIR, prefix + ".pdf")

        # Write to disk
        write_pdf(pdf_path, resume_text)

        self.logger.info(f"ResumeAgent: saved PDF → {pdf_path}")

        # -------------------------
        # Insert DB record
        # -------------------------
        db = SessionLocal()
        try:
            pkg = ApplicationPackage(
                job_id=job_id,
                title=title,
                company=company,
                score=str(score),
                resume_path=pdf_path,
                cover_letter_path=None,
                package_metadata={"agent": "ResumeAgent"}
            )
            db.add(pkg)
            db.commit()
            db.refresh(pkg)
        except Exception as e:
            db.rollback()
            self.logger.error(f"ResumeAgent: DB error: {e}")
            return
        finally:
            db.close()

        # -------------------------
        # Update State
        # -------------------------
        self.state["completed_resumes"][str(job_id)] = {
            "job_id": job_id,
            "title": title,
            "company": company,
            "resume_pdf": pdf_path,
            "score": score
        }

        self.logger.info(f"ResumeAgent: DONE job {job_id}")

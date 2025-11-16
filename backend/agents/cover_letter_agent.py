import os
import re
from typing import Dict, Any, Optional

from .base import BaseAgent, AgentConfig
from backend.utils.pdf_writer import write_pdf
from backend.db.repo import SessionLocal
from backend.db.models import ApplicationPackage


def safe_filename(text: str) -> str:
    text = text.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_]+", "", text)


BASE_DIR = "backend/generated"
CL_DIR = os.path.join(BASE_DIR, "cover_letters")
os.makedirs(CL_DIR, exist_ok=True)


class CoverLetterAgent(BaseAgent):

    def __init__(self, config: AgentConfig):
        super().__init__("CoverLetterAgent", config)

        if "completed_cover_letters" not in self.state:
            self.state["completed_cover_letters"] = {}

    def fetch_job(self, job_id: int):
        return self.api_get(f"/jobs/{job_id}")

    def generate_cl(self, title: str, company: str, description: str):
        payload = {
            "title": title,
            "company": company,
            "description": description,
            "top_k": 5
        }
        resp = self.api_post("/jobs/generate_cover_letter", payload)
        if not resp:
            return None
        return resp.get("generated_cover_letter")

    def get_next_match(self):
        matches = self.state.get("strong_matches", [])
        if matches:
            return matches.pop(0)
        return None

    def is_completed(self, job_id: int):
        return str(job_id) in self.state["completed_cover_letters"]

    def step(self):

        self.logger.info("CoverLetterAgent: checking matches...")

        match = self.get_next_match()
        if not match:
            self.logger.info("CoverLetterAgent: no matches.")
            return

        job_id = match["job_id"]
        score = match["score"]

        if self.is_completed(job_id):
            return

        job = self.fetch_job(job_id)
        if not job:
            return

        title = job.get("title", "")
        company = job.get("company", "")
        description = job.get("description", "")

        cl_text = self.generate_cl(title, company, description)
        if cl_text is None:
            self.logger.error(f"CoverLetterAgent failed job {job_id}")
            return

        prefix = f"{job_id}_{safe_filename(company)}_{safe_filename(title)}"
        pdf_path = os.path.join(CL_DIR, prefix + ".pdf")
        write_pdf(pdf_path, cl_text)

        self.logger.info(f"CoverLetterAgent: saved PDF → {pdf_path}")

        db = SessionLocal()
        try:
            pkg = ApplicationPackage(
                job_id=job_id,
                title=title,
                company=company,
                score=str(score),
                resume_path=None,
                cover_letter_path=pdf_path,
                package_metadata={"agent": "CoverLetterAgent"}
            )
            db.add(pkg)
            db.commit()
        except:
            db.rollback()
        finally:
            db.close()

        self.state["completed_cover_letters"][str(job_id)] = {
            "job_id": job_id,
            "title": title,
            "company": company,
            "cover_letter_pdf": pdf_path,
            "score": score
        }

        self.logger.info(f"CoverLetterAgent: DONE job {job_id}")

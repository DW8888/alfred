import os
import re
from typing import Dict, Any, Optional

from .base import BaseAgent, AgentConfig
from backend.utils.pdf_writer import write_pdf
from backend.db.repo import SessionLocal
from backend.db.models import ApplicationPackage, GeneratedArtifact  # make sure this model exists
from dotenv import load_dotenv



def safe_filename(text: str) -> str:
    text = text.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_]+", "", text)


BASE_DIR = "backend/generated"
CL_DIR = os.path.join(BASE_DIR, "cover_letters")
os.makedirs(CL_DIR, exist_ok=True)


class CoverLetterAgent(BaseAgent):
    """
    CoverLetterAgent V2

    Responsibilities:
      - Pops "strong match" jobs from agent state.
      - Fetches job details from /jobs/{id}.
      - Calls /jobs/generate_cover_letter to generate tailored CL text.
      - Writes a PDF copy to backend/generated/cover_letters.
      - Persists metadata into ApplicationPackage.
      - Persists full text into GeneratedArtifact (artifact_type='cover_letter').
      - Tracks completed cover letters in agent state.
    """

    def __init__(self, config: AgentConfig):
        super().__init__("CoverLetterAgent", config)

        if "completed_cover_letters" not in self.state:
            self.state["completed_cover_letters"] = {}

    # -------------------------
    # Backend Helpers
    # -------------------------
    def fetch_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        return self.api_get(f"/jobs/{job_id}")

    def generate_cover_letter(
        self,
        title: str,
        company: str,
        description: str,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        payload: Dict[str, Any] = {
            "title": title,
            "company": company,
            "description": description,
            "top_k": 5,
        }
        if extra_config:
            payload["config"] = extra_config

        resp = self.api_post("/jobs/generate_cover_letter", payload)
        if not resp:
            return None
        return resp.get("generated_cover_letter")

    # -------------------------
    # State Helpers
    # -------------------------
    def get_next_match(self) -> Optional[Dict[str, Any]]:
        matches = self.state.get("strong_matches", [])
        if matches:
            return matches.pop(0)
        return None

    def is_completed(self, job_id: int) -> bool:
        return str(job_id) in self.state["completed_cover_letters"]

    def mark_completed(
        self,
        job_id: int,
        title: str,
        company: str,
        pdf_path: str,
        score: Any,
    ) -> None:
        self.state["completed_cover_letters"][str(job_id)] = {
            "job_id": job_id,
            "title": title,
            "company": company,
            "cover_letter_pdf": pdf_path,
            "score": score,
        }

    # -------------------------
    # Main Step
    # -------------------------
    def step(self) -> None:

        self.logger.info("CoverLetterAgent: checking matches...")

        match = self.get_next_match()
        if not match:
            self.logger.info("CoverLetterAgent: no matches.")
            return

        job_id = match.get("job_id")
        score = match.get("score")

        if job_id is None:
            self.logger.error("CoverLetterAgent: malformed match, missing job_id.")
            return

        if self.is_completed(job_id):
            self.logger.info(f"CoverLetterAgent: job {job_id} already processed.")
            return

        job = self.fetch_job(job_id)
        if not job:
            self.logger.error(f"CoverLetterAgent: failed to fetch job {job_id}")
            return

        title = job.get("title", "")
        company = job.get("company", "")
        description = job.get("description", "")

        # Optional future config hook (role, template, tone, etc.)
        extra_config: Dict[str, Any] = {}

        cl_text = self.generate_cover_letter(title, company, description, extra_config)
        if cl_text is None:
            self.logger.error(f"CoverLetterAgent: generation failed for job {job_id}")
            return

        prefix = f"{job_id}_{safe_filename(company)}_{safe_filename(title)}"
        pdf_path = os.path.join(CL_DIR, prefix + ".pdf")

        try:
            write_pdf(pdf_path, cl_text)
        except Exception as e:
            self.logger.error(f"CoverLetterAgent: failed writing PDF for job {job_id}: {e}")
            return

        self.logger.info(f"CoverLetterAgent: saved PDF → {pdf_path}")

        db = SessionLocal()
        try:
            # 1) ApplicationPackage: store cover letter file path
            pkg = ApplicationPackage(
                job_id=job_id,
                title=title,
                company=company,
                score=str(score) if score is not None else None,
                resume_path=None,
                cover_letter_path=pdf_path,
                package_metadata={"agent": "CoverLetterAgent"},
            )
            db.add(pkg)

            # 2) GeneratedArtifact: store full text
            ga = GeneratedArtifact(
                job_id=job_id,
                job_title=title,
                company=company,
                artifact_type="cover_letter",
                content=cl_text,
            )
            db.add(ga)

            db.commit()
            db.refresh(pkg)
            db.refresh(ga)

            self.logger.info(
                f"CoverLetterAgent: DB records created → "
                f"ApplicationPackage.id={pkg.id}, GeneratedArtifact.id={ga.id}"
            )

        except Exception as e:
            db.rollback()
            self.logger.error(f"CoverLetterAgent: DB error for job {job_id}: {e}")
            return
        finally:
            db.close()

        self.mark_completed(job_id, title, company, pdf_path, score)
        self.logger.info(f"CoverLetterAgent: DONE job {job_id}")
# ---------------------------------------------------------
# Manual Launcher
# ---------------------------------------------------------
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    from backend.agents.base import AgentConfig

    load_dotenv()

    api_base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

    config = AgentConfig(
        backend_url=api_base,
        state_path="cover_letter_agent_state.json",
        sleep_interval=10     # or 0 for single-shot
    )

    agent = CoverLetterAgent(config)
    # print("===>>> CoverLetterAgent starting...")
    agent.run()

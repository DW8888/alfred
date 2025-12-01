import os
import re
from typing import Dict, Any, Optional

from dotenv import load_dotenv

from .base import BaseAgent, AgentConfig
from backend.queue.simple_queue import SimpleQueue
from backend.utils.pdf_writer import write_pdf
from backend.db.repo import SessionLocal
from backend.db.models import ApplicationPackage, GeneratedArtifact


# -------------------------------------------------------------------
# Filename Sanitizer
# -------------------------------------------------------------------
def safe_filename(text: str) -> str:
    text = text.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_]+", "", text)


# -------------------------------------------------------------------
# Output Directories
# -------------------------------------------------------------------
BASE_DIR = "backend/generated"
RESUME_DIR = os.path.join(BASE_DIR, "resumes")
os.makedirs(RESUME_DIR, exist_ok=True)


class ResumeAgent(BaseAgent):
    """
    ResumeAgent V3 (Queue-Based)
    -----------------------------
    Responsibilities:

      1. Pull a job request from resume_queue.json
      2. Fetch job details from backend
      3. Generate resume text via /jobs/generate_resume
      4. Save resume to PDF
      5. Store result in:
           - ApplicationPackage
           - GeneratedArtifact (artifact_type='resume')
      6. Push job forward into cover_letter_queue.json
      7. Mark job as completed in internal state

    This agent does NOT decide how resumes are written.
    The logic lives inside /jobs/generate_resume.
    """

    def __init__(self, config: AgentConfig):
        super().__init__("ResumeAgent", config)

        # Local state: avoid reprocessing already-completed jobs
        self.state.setdefault("completed_resumes", {})

        # Queue: incoming strong matches
        self.resume_queue = SimpleQueue("resume_queue.json")

        # Queue: downstream for cover letters
        self.cover_letter_queue = SimpleQueue("cover_letter_queue.json")

    # -------------------------------------------------------------------
    # Backend Helpers
    # -------------------------------------------------------------------
    def fetch_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        return self.api_get(f"/jobs/{job_id}")

    def generate_resume(
        self,
        title: str,
        company: str,
        description: str,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:

        payload = {
            "title": title,
            "company": company,
            "description": description,
            "top_k": 5,
        }

        if extra_config:
            payload["config"] = extra_config

        resp = self.api_post("/jobs/generate_resume", payload)
        if not resp:
            return None

        return resp.get("generated_resume")

    # -------------------------------------------------------------------
    # Main Step
    # -------------------------------------------------------------------
    def step(self):

        self.logger.info("===>>> ResumeAgent: polling resume_queue.json...")

        job_item = self.resume_queue.pop()

        if not job_item:
            self.logger.info("ResumeAgent: queue empty.")
            return

        job_id = job_item.get("job_id")
        score = job_item.get("score", 0)

        if job_id is None:
            self.logger.error("--XX-- Malformed queue message: missing job_id")
            return

        if str(job_id) in self.state["completed_resumes"]:
            self.logger.info(f"--OK-- Resume already generated for job {job_id}")
            return

        # Fetch job details
        job = self.fetch_job(job_id)
        if not job:
            self.logger.error(f"--XX-- Unable to fetch job {job_id}")
            return

        title = job.get("title", "")
        company = job.get("company", "")
        description = job.get("description", "")

        # -------------------------------------------------------------------
        # Generate Resume
        # -------------------------------------------------------------------
        resume_text = self.generate_resume(title, company, description)
        if resume_text is None:
            self.logger.error(f"--XX-- Resume generation failed for job {job_id}")
            return

        # Write PDF
        filename_prefix = f"{job_id}_{safe_filename(company)}_{safe_filename(title)}"
        pdf_path = os.path.join(RESUME_DIR, filename_prefix + ".pdf")

        try:
            write_pdf(pdf_path, resume_text)
        except Exception as e:
            self.logger.error(f"--XX-- Failed writing PDF for job {job_id}: {e}")
            return

        self.logger.info(f"--OK-- PDF saved → {pdf_path}")

        # -------------------------------------------------------------------
        # Save to DB
        # -------------------------------------------------------------------
        db = SessionLocal()
        try:
            # Application Package record
            pkg = ApplicationPackage(
                job_id=job_id,
                title=title,
                company=company,
                score=str(score),
                resume_path=pdf_path,
                cover_letter_path=None,
                package_metadata={"agent": "ResumeAgent"},
            )
            db.add(pkg)

            # Save full text into GeneratedArtifact
            ga = GeneratedArtifact(
                job_title=title,
                company=company,
                artifact_type="resume",
                content=resume_text,
            )
            db.add(ga)

            db.commit()
            db.refresh(pkg)
            db.refresh(ga)

            self.logger.info(
                f"--OK-- DB saved: ApplicationPackage.id={pkg.id}, GeneratedArtifact.id={ga.id}"
            )

        except Exception as e:
            db.rollback()
            self.logger.error(f"--XX-- DB error for job {job_id}: {e}")
            return
        finally:
            db.close()

        # -------------------------------------------------------------------
        # Push job to next queue: cover letters
        # -------------------------------------------------------------------
        self.cover_letter_queue.push({
            "job_id": job_id,
            "score": score,
            "title": title,
            "company": company,
        })

        # -------------------------------------------------------------------
        # Mark complete
        # -------------------------------------------------------------------
        self.state["completed_resumes"][str(job_id)] = {
            "job_id": job_id,
            "title": title,
            "company": company,
            "score": score,
            "resume_pdf": pdf_path,
        }
        self._save_state()

        self.logger.info(f"--OK-- ResumeAgent: DONE job {job_id}")


# -------------------------------------------------------------------
# Launcher
# -------------------------------------------------------------------
if __name__ == "__main__":
    load_dotenv()

    api_base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

    config = AgentConfig(
        backend_url=api_base,
        state_path="resume_agent_state.json",
        sleep_interval=5,
    )

    agent = ResumeAgent(config)
    print("===>>> ResumeAgent starting...")
    agent.run()

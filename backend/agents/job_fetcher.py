from dotenv import load_dotenv
load_dotenv()
import os
import requests
from typing import List, Dict, Optional, Any
from .base import BaseAgent, AgentConfig


class JobFetcherAgent(BaseAgent):
    """
    Fetch jobs from Adzuna and insert them into the backend.
    Includes dedupe so we don't reinsert the same job repeatedly.
    """

    BASE_URL = "https://api.adzuna.com/v1/api/jobs/us/search/1"

    def __init__(self, config: AgentConfig):
        super().__init__("JobFetcher", config)

        # -----------------------------------------
        # DEDUPE: track URLs we've already submitted
        # -----------------------------------------
        if "seen_job_urls" not in self.state:
            self.state["seen_job_urls"] = []

    def fetch_adzuna_jobs(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch Data Engineering jobs in NYC from Adzuna."""

        app_id = os.getenv("ADZUNA_AI_ID")
        api_key = os.getenv("ADZUNA_API_KEY")

        if not app_id or not api_key:
            self.logger.error("❌ ADZUNA_API_KEY or ADZUNA_AI_ID missing")
            return None

        params = {
            "app_id": app_id,
            "app_key": api_key,
            "what": "data engineer",
            "where": "New York City",
            "results_per_page": 20,
            "content-type": "application/json"
        }

        try:
            response = requests.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            return response.json().get("results", [])
        except Exception as e:
            self.logger.error(f"❌ Adzuna request failed: {e}")
            return None

    def insert_job(self, job: Dict[str, Any]):
        """Send job to FastAPI with dedupe protection."""

        url = job.get("redirect_url")

        # -----------------------------------------
        # HARD DEDUPE: Skip jobs we've already seen
        # -----------------------------------------
        if url and url in self.state["seen_job_urls"]:
            self.logger.info(f"⏭️ Skipping already-seen job: {job.get('title')}")
            return

        payload = {
            "title": job.get("title", "Unknown Title"),
            "company": job.get("company", {}).get("display_name", ""),
            "location": job.get("location", {}).get("display_name", ""),
            "description": job.get("description", "")[:4000],
            "source_url": url or ""
        }

        resp = self.api_post("/jobs/", payload)

        if resp and resp.get("duplicate"):
            self.logger.info(f"⏭️ Duplicate skipped: {payload['title']}")
        elif resp:
            self.logger.info(f"✔️ Inserted job: {payload['title']}")
        else:
            self.logger.error("❌ Failed to insert job into backend")


        # -----------------------------------------
        # Add to seen list after successful insert
        # -----------------------------------------
        if url:
            self.state["seen_job_urls"].append(url)
            self._save_state()

        self.logger.info(f"✔️ Inserted job: {payload['title']}")

    def step(self):
        self.logger.info("🔍 Fetcher: checking Adzuna for new jobs...")
        print("DEBUG:", os.getenv("ADZUNA_AI_ID"), os.getenv("ADZUNA_API_KEY"))

        jobs = self.fetch_adzuna_jobs()
        if not jobs:
            self.logger.info("ℹ️ No jobs found.")
            return

        for job in jobs:
            self.insert_job(job)

        self.logger.info("✅ Fetch cycle complete.")


# -----------------------------
# Main launcher
# -----------------------------
if __name__ == "__main__":
    api_base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

    config = AgentConfig(
        backend_url=api_base,
        state_path="fetcher_state.json",
        sleep_interval=30
    )

    agent = JobFetcherAgent(config)
    print("➡️ JobFetcherAgent starting...")
    agent.run()


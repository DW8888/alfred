# backend/agents/job_fetcher.py
from dotenv import load_dotenv
load_dotenv()

import os
import hashlib
import requests
from typing import List, Dict, Optional, Any

from .base import BaseAgent, AgentConfig


class JobFetcherAgent(BaseAgent):
    """
    Fetch jobs from Adzuna and insert them into the backend.
    Includes dedupe so we don't reinsert the same job repeatedly.
    """

    BASE_URL = "https://api.adzuna.com/v1/api/jobs/us/search"
    MAX_PAGES = 3  # fetch first 3 pages -> up to ~60 jobs

    def __init__(self, config: AgentConfig):
        super().__init__("JobFetcher", config)

        # -----------------------------------------
        # DEDUPE: track fingerprints we've already submitted
        # -----------------------------------------
        if "seen_job_hashes" not in self.state:
            self.state["seen_job_hashes"] = []

    # -----------------------------------------
    # Helper: job fingerprint
    # -----------------------------------------
    def job_fingerprint(self, job: Dict[str, Any]) -> str:
        """
        Deterministic hash based on title + company + description.
        This survives redirect_url churn.
        """
        title = job.get("title", "") or ""
        company = (job.get("company", {}) or {}).get("display_name", "") or ""
        desc = job.get("description", "") or ""
        key = (title + "|" + company + "|" + desc).strip().lower()
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def fetch_adzuna_jobs(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch Data Engineering jobs in NYC from Adzuna with basic pagination."""

        app_id = os.getenv("ADZUNA_AI_ID")
        api_key = os.getenv("ADZUNA_API_KEY")

        if not app_id or not api_key:
            self.logger.error("--XX-- ADZUNA_API_KEY or ADZUNA_AI_ID missing")
            return None

        all_results: List[Dict[str, Any]] = []

        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.BASE_URL}/{page}"

            params = {
                "app_id": app_id,
                "app_key": api_key,
                "what": "data engineer",
                "where": "New York City",
                "results_per_page": 20,
                "content-type": "application/json",
            }

            try:
                resp = requests.get(url, params=params, timeout=30)
                resp.raise_for_status()
                page_results = resp.json().get("results", [])
                if not page_results:
                    break
                all_results.extend(page_results)
            except Exception as e:
                self.logger.error(f"--XX-- Adzuna request failed on page {page}: {e}")
                break

        return all_results

    def insert_job(self, job: Dict[str, Any]):
        """Send job to FastAPI with dedupe protection."""

        url = job.get("redirect_url", "") or ""
        fp = self.job_fingerprint(job)

        # -----------------------------------------
        # HARD DEDUPE: Skip jobs we've already seen via fingerprint
        # -----------------------------------------
        if fp in self.state["seen_job_hashes"]:
            self.logger.info(f">>-->> Skipping already-seen job (hash): {job.get('title')}")
            return

        payload = {
            "title": job.get("title", "Unknown Title"),
            "company": job.get("company", {}).get("display_name", ""),
            "location": job.get("location", {}).get("display_name", ""),
            "description": job.get("description", "")[:4000],
            "source_url": url,
        }

        resp = self.api_post("/jobs/", payload)

        if resp and resp.get("duplicate"):
            self.logger.info(f">>==>> Duplicate skipped (backend): {payload['title']}")
        elif resp:
            self.logger.info(f"--OK-- Inserted job: {payload['title']}")
        else:
            self.logger.error("--XX-- Failed to insert job into backend")
            return

        # -----------------------------------------
        # Add to seen list after successful insert
        # -----------------------------------------
        self.state["seen_job_hashes"].append(fp)

        # keep dedupe list from exploding
        if len(self.state["seen_job_hashes"]) > 2000:
            self.state["seen_job_hashes"] = self.state["seen_job_hashes"][-1000:]

        self._save_state()

    def step(self):
        self.logger.info("===>>> JobFetcher: checking Adzuna for new jobs...")
        print("DEBUG:", os.getenv("ADZUNA_AI_ID"), os.getenv("ADZUNA_API_KEY"))

        jobs = self.fetch_adzuna_jobs()
        if not jobs:
            self.logger.info("!! No jobs found.")
            return

        for job in jobs:
            self.insert_job(job)

        self.logger.info("--OK-- JobFetcher: fetch cycle complete.")


# -----------------------------
# Main launcher
# -----------------------------
if __name__ == "__main__":
    api_base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

    config = AgentConfig(
        backend_url=api_base,
        state_path="fetcher_state.json",
        sleep_interval=3300,  # 55 minutes
    )

    agent = JobFetcherAgent(config)
    print("===>>> JobFetcherAgent starting...")
    agent.run()

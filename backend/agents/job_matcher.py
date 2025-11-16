from typing import List, Dict, Any, Optional

from .base import BaseAgent, AgentConfig


class JobMatcherAgent(BaseAgent):
    """
    Agent Responsibilities:
      - Retrieve job descriptions from backend
      - Identify new or unprocessed jobs
      - Run vector similarity matching via /jobs/match
      - Store match results persistently
      - Forward strong matches for other agents
    """

    MATCH_THRESHOLD = 0.75  # Adjust based on embeddings quality

    def __init__(self, config: AgentConfig):
        super().__init__("JobMatcher", config)

        # Initialize state keys if missing
        if "processed_jobs" not in self.state:
            self.state["processed_jobs"] = {}
        if "strong_matches" not in self.state:
            self.state["strong_matches"] = []

    # ----------------------------------------------------------------------
    # Utilities
    # ----------------------------------------------------------------------
    def fetch_jobs(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch all jobs from the backend."""
        resp = self.api_get("/jobs/")
        if resp is None:
            return None

        if "jobs" in resp:
            return resp["jobs"]

        return resp  # If backend simply returns list

    def match_job(self, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Run vector similarity search on a job description."""
        payload = {
    "title": job.get("title", ""),
    "company": job.get("company", "") or "",
    "description": job.get("description", "") or "",
    "top_k": 10
    }

        return self.api_post("/jobs/match", payload)

    # ----------------------------------------------------------------------
    # Core Logic
    # ----------------------------------------------------------------------
    def is_processed(self, job_id: int) -> bool:
        """Check if job was already matched."""
        return str(job_id) in self.state["processed_jobs"]

    def evaluate_match_strength(self, match_results: Dict[str, Any]) -> float:
        """
        Compute average similarity score from /jobs/match response.
        """
        matches = match_results.get("matches", [])
        if not matches:
            return 0.0

        scores = [m.get("similarity", 0.0) for m in matches]
        return sum(scores) / len(scores)


    # ----------------------------------------------------------------------
    # Main Loop Step
    # ----------------------------------------------------------------------
    def step(self):
        self.logger.info("Polling for new jobs...")

        jobs = self.fetch_jobs()
        if jobs is None:
            self.logger.error("Failed to fetch jobs.")
            return

        for job in jobs:
            job_id = job.get("id")

            if job_id is None:
                continue

            # Skip if already processed
            if self.is_processed(job_id):
                continue

            self.logger.info(f"Processing job {job_id}: {job.get('title', 'Unknown')}")

            # Perform vector matching
            results = self.match_job(job)
            if results is None:
                self.logger.error(f"Matching failed for job {job_id}")
                continue

            score = self.evaluate_match_strength(results)
            self.logger.info(f"Match score for job {job_id}: {score:.4f}")

            # Save results in persistent state
            self.state["processed_jobs"][str(job_id)] = {
        "score": score,
        "matches": results.get("matches", [])
            }


            # Flag strong matches
            if score >= self.MATCH_THRESHOLD:
                self.state["strong_matches"].append({
                    "job_id": job_id,
                    "title": job.get("title"),
                    "score": score,
                })

                self.logger.info(f"Strong match found for job {job_id} (score {score:.4f})")

        self.logger.info("JobMatcher step complete.")
if __name__ == "__main__":
    import os
    from backend.agents.base import AgentConfig

    api_base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

    config = AgentConfig(
        backend_url=api_base,      # <-- FIXED NAME
        state_path="matcher_state.json",
        sleep_interval=5
    )

    agent = JobMatcherAgent(config)
    print("➡️ JobMatcherAgent starting...")
    agent.run()


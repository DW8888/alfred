# backend/agents/job_matcher.py
from typing import List, Dict, Any, Optional

from backend.queue.simple_queue import SimpleQueue
from .base import BaseAgent, AgentConfig


class JobMatcherAgent(BaseAgent):
    """
    Hybrid Job Matcher
    ------------------
    Matches job descriptions to user artifacts using:
      - semantic similarity
      - (LLM) skill overlap via /jobs/match
      - combined hybrid score (computed in backend)

    Produces:
      processed_jobs[job_id] = { score, matches }

    Strong matches are pushed into:
      resume_queue.json
    """

    MATCH_THRESHOLD = 0.46  # tuned empirically for combined_score
    MIN_DESC_LEN = 80       # ignore ultra-short / broken job posts

    def __init__(self, config: AgentConfig):
        super().__init__("JobMatcher", config)

        self.state.setdefault("processed_jobs", {})

        # Queue used to send work to ResumeAgent
        self.resume_queue = SimpleQueue("resume_queue.json")

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------
    def fetch_jobs(self) -> Optional[List[Dict[str, Any]]]:
        resp = self.api_get("/jobs/")
        if resp is None:
            return None

        if isinstance(resp, dict) and "jobs" in resp:
            return resp["jobs"]

        return resp

    def match_job(self, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload = {
            "title": job.get("title", ""),
            "company": job.get("company", "") or "",
            "description": job.get("description", "") or "",
            "top_k": 10,
        }
        return self.api_post("/jobs/match", payload)

    def is_processed(self, job_id: int) -> bool:
        return str(job_id) in self.state["processed_jobs"]

    def evaluate_match_strength(self, match_results: Dict[str, Any]) -> float:
        matches = match_results.get("matches", [])
        if not matches:
            return 0.0

        scores: List[float] = []
        for m in matches:
            if "combined_score" in m:
                scores.append(float(m["combined_score"]))
            elif "similarity" in m:
                scores.append(float(m["similarity"]))

        if not scores:
            return 0.0

        return sum(scores) / len(scores)

    # ----------------------------------------------------------
    # Main Step
    # ----------------------------------------------------------
    def step(self):

        self.logger.info("===>>> JobMatcher: polling backend for new jobs...")

        jobs = self.fetch_jobs()
        if jobs is None:
            self.logger.error("--XX-- Backend returned no jobs")
            return

        # Clean stale processed jobs
        existing_ids = {j.get("id") for j in jobs if j.get("id") is not None}
        stored_ids = set(self.state["processed_jobs"].keys())

        for stale in stored_ids - {str(i) for i in existing_ids}:
            del self.state["processed_jobs"][stale]

        for job in jobs:
            job_id = job.get("id")
            if job_id is None:
                continue

            title = job.get("title", "Unknown")
            desc = job.get("description", "") or ""

            # Already processed?
            if self.is_processed(job_id):
                continue

            # Skip garbage posts
            if len(desc) < self.MIN_DESC_LEN:
                self.logger.info(f"--XX-- Skipping job {job_id} (description too short)")
                self.state["processed_jobs"][str(job_id)] = {
                    "score": 0.0,
                    "matches": [],
                }
                self._save_state()
                continue

            self.logger.info(f"===>>> Matching job {job_id}: {title}")

            results = self.match_job(job)
            if results is None:
                self.logger.error(f"--XX-- /jobs/match failed for job {job_id}")
                continue

            score = self.evaluate_match_strength(results)
            self.logger.info(f"===>>> Hybrid score for job {job_id}: {score:.4f}")

            # Save processed record
            self.state["processed_jobs"][str(job_id)] = {
                "score": score,
                "matches": results.get("matches", []),
            }
            self._save_state()

            # ----------------------------------------------------------
            # Strong Match → push to resume queue
            # ----------------------------------------------------------
            if score >= self.MATCH_THRESHOLD:
                self.logger.info(
                    f"--OK-- Strong match detected (score={score:.4f}) for job {job_id}"
                )

                self.resume_queue.push({
                    "job_id": job_id,
                    "title": title,
                    "score": score,
                })

        self.logger.info("--OK-- JobMatcher step complete.")


# ----------------------------------------------------------
# Standalone Launcher
# ----------------------------------------------------------
if __name__ == "__main__":
    import os
    from backend.agents.base import AgentConfig

    api_base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

    config = AgentConfig(
        backend_url=api_base,
        state_path="matcher_state.json",
        sleep_interval=5,
    )

    agent = JobMatcherAgent(config)
    print("===>>> JobMatcherAgent starting...")
    agent.run()

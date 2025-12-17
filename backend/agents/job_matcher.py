# backend/agents/job_matcher.py
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import List, Dict, Any, Optional, Tuple

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

    MATCH_THRESHOLD = 0.6  # tightened to require stronger matches
    MIN_DESC_LEN = 80       # ignore ultra-short / broken job posts
    DEFAULT_MAX_WORKERS = 4
    SKIP_POSTINGS: Tuple[Tuple[str, str], ...] = (
        ("data engineer / senior data engineer (ai/ml)", "applied systems inc"),
        ("data engineer / senior data engineer (gcp, bigquery)", "applied systems inc"),
        ("data engineer", "dl software inc."),
        ("data engineer", "pixelplex"),
    )

    def __init__(self, config: AgentConfig):
        super().__init__("JobMatcher", config)

        self.state.setdefault("processed_jobs", {})
        self.state.setdefault("queued_jobs", {})
        self.state.setdefault("skipped_jobs", {})
        self.state.setdefault("processed_signatures", {})

        self._state_lock = Lock()
        self.max_workers = max(
            1,
            int(os.getenv("JOB_MATCHER_WORKERS", self.DEFAULT_MAX_WORKERS)),
        )

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
            "job_id": job.get("id"),
            "title": job.get("title", ""),
            "company": job.get("company", "") or "",
            "description": job.get("description", "") or "",
            "top_k": 10,
        }
        return self.api_post("/jobs/match", payload)

    def is_processed(self, job_id: int) -> bool:
        return str(job_id) in self.state["processed_jobs"]

    def has_been_queued(self, job_id: int) -> bool:
        return str(job_id) in self.state["queued_jobs"]

    def should_skip_posting(self, title: str, company: str) -> bool:
        key = (title.strip().lower(), (company or "").strip().lower())
        return key in self.SKIP_POSTINGS

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

    def _mark_processed_short_desc(self, job_id: int):
        with self._state_lock:
            self.state["processed_jobs"][str(job_id)] = {
                "score": 0.0,
                "matches": [],
            }
            self._save_state()

    def _record_processed(self, job_id: int, score: float, matches: List[Dict[str, Any]]):
        with self._state_lock:
            self.state["processed_jobs"][str(job_id)] = {
                "score": score,
                "matches": matches,
            }
            self._save_state()

    def _record_queue_entry(self, job_id: int, score: float, title: str, company: str):
        with self._state_lock:
            self.state["queued_jobs"][str(job_id)] = {
                "score": score,
                "title": title,
                "company": company,
            }
            self._save_state()

    def _record_skip(self, job_id: int, score: float, title: str, company: str):
        with self._state_lock:
            self.state["skipped_jobs"][str(job_id)] = {
                "score": score,
                "title": title,
                "company": company,
            }
            self._save_state()

    def _process_single_job(self, job: Dict[str, Any]) -> None:
        job_id = job.get("id")
        title = job.get("title", "Unknown")
        company = job.get("company", "") or ""

        self.logger.info(f"===>>> Matching job {job_id}: {title}")

        results = self.match_job(job)
        if results is None:
            self.logger.error(f"--XX-- /jobs/match failed for job {job_id}")
            return

        score = self.evaluate_match_strength(results)
        self.logger.info(f"===>>> Hybrid score for job {job_id}: {score:.4f}")

        self._record_processed(job_id, score, results.get("matches", []))

        if self.should_skip_posting(title, company):
            self.logger.info(
                f"--XX-- Skipping job {job_id} ({title} @ {company}) per skip list"
            )
            self._record_skip(job_id, score, title, company)
            return

        if score >= self.MATCH_THRESHOLD and not self.has_been_queued(job_id):
            self.logger.info(
                f"--OK-- Strong match detected (score={score:.4f}) for job {job_id}"
            )

            self.resume_queue.push({
                "job_id": job_id,
                "title": title,
                "score": score,
            })
            self._record_queue_entry(job_id, score, title, company)

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
        existing_id_strs = {str(i) for i in existing_ids}
        stored_ids = set(self.state["processed_jobs"].keys())

        for stale in stored_ids - existing_id_strs:
            del self.state["processed_jobs"][stale]
        queued_ids = set(self.state["queued_jobs"].keys())
        for stale in queued_ids - existing_id_strs:
            del self.state["queued_jobs"][stale]

        candidates: List[Dict[str, Any]] = []

        for job in jobs:
            job_id = job.get("id")
            if job_id is None:
                continue

            desc = job.get("description", "") or ""

            # Already processed?
            if self.is_processed(job_id):
                continue

            # Skip garbage posts
            if len(desc) < self.MIN_DESC_LEN:
                self.logger.info(f"--XX-- Skipping job {job_id} (description too short)")
                self._mark_processed_short_desc(job_id)
                continue

            candidates.append(job)

        if not candidates:
            self.logger.info("--OK-- No new jobs to process.")
            return

        self.logger.info(
            f"-->> Dispatching {len(candidates)} jobs across {self.max_workers} workers."
        )

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(self._process_single_job, job)
                for job in candidates
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    self.logger.error(f"--XX-- Worker crashed: {exc}")

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
    # print("===>>> JobMatcherAgent starting...")
    agent.run()

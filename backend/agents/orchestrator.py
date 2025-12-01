# backend/agents/orchestrator.py
import time
import threading
import traceback
import os
from dotenv import load_dotenv

from backend.agents.base import AgentConfig
from backend.agents.job_fetcher import JobFetcherAgent
from backend.agents.job_matcher import JobMatcherAgent
from backend.agents.resume_agent import ResumeAgent
from backend.agents.cover_letter_agent import CoverLetterAgent
from backend.agents.github_ingestion_agent import GitHubIngestionAgent
from backend.queue.simple_queue import SimpleQueue

# Global queues shared across agents
resume_queue = SimpleQueue("resume_queue.json")
cover_queue = SimpleQueue("cover_letter_queue.json")


class Orchestrator:
    """
    Runs all agents on independent schedules using multi-threading.
    Applies dependency logic so agents run only when prerequisites are met.
    """

    def __init__(self):
        load_dotenv()

        backend_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

        github_username = os.getenv("GITHUB_USERNAME")
        github_token = os.getenv("GITHUB_TOKEN")

        if not github_username:
            raise ValueError("--XX-- Missing GITHUB_USERNAME in .env")
        if not github_token:
            raise ValueError("--XX-- Missing GITHUB_TOKEN in .env")

        # ------------------------------
        # Agents and schedules
        # ------------------------------
        self.agents = {
            "github_ingestion": {
                "instance": GitHubIngestionAgent(
                    AgentConfig(
                        backend_url=backend_url,
                        state_path="state_github_ingestion.json",
                        sleep_interval=5,
                    ),
                    github_username=github_username,
                    github_token=github_token,
                ),
                "interval": 60 * 60 * 24,  # 24 hours
                "last_run": 0,
            },

            "job_fetcher": {
                "instance": JobFetcherAgent(
                    AgentConfig(
                        backend_url=backend_url,
                        state_path="state_job_fetcher.json",
                        sleep_interval=5,
                    )
                ),
                "interval": 60 * 60,  # 1 hour
                "last_run": 0,
            },

            "job_matcher": {
                "instance": JobMatcherAgent(
                    AgentConfig(
                        backend_url=backend_url,
                        state_path="state_job_matcher.json",
                        sleep_interval=5,
                    )
                ),
                "interval": 60 * 5,  # 5 minutes
                "last_run": 0,
            },

            "resume_agent": {
                "instance": ResumeAgent(
                    AgentConfig(
                        backend_url=backend_url,
                        state_path="state_resume_agent.json",
                        sleep_interval=5,
                    )
                ),
                "interval": 60 * 5,
                "last_run": 0,
            },

            "cover_letter_agent": {
                "instance": CoverLetterAgent(
                    AgentConfig(
                        backend_url=backend_url,
                        state_path="state_cover_letter_agent.json",
                        sleep_interval=5,
                    )
                ),
                "interval": 60 * 5,
                "last_run": 0,
            },
        }

    # ------------------------------------------------------------------
    def run_agent_once(self, name: str, agent_obj):
        try:
            print(f"===>>> Running {name}.step()")
            agent_obj.step()
            print(f"--OK-- {name} completed")
        except Exception as e:
            print(f"--XX-- Agent {name} crashed: {e}")
            traceback.print_exc()

    # ------------------------------------------------------------------
    def start(self):
        print("===>>> Alfred Orchestrator started")

        while True:
            now = time.time()

            for name, cfg in self.agents.items():
                interval = cfg["interval"]
                last_run = cfg["last_run"]

                # Conditional logic for downstream agents
                if name == "resume_agent" and resume_queue.size() == 0:
                    continue

                if name == "cover_letter_agent" and cover_queue.size() == 0:
                    continue

                # Time to run?
                if now - last_run >= interval:
                    thread = threading.Thread(
                        target=self.run_agent_once,
                        args=(name, cfg["instance"]),
                        daemon=True,
                    )
                    thread.start()
                    cfg["last_run"] = now

            time.sleep(5)


if __name__ == "__main__":
    orchestrator = Orchestrator()
    orchestrator.start()

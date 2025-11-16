import time
import threading
import traceback
import os
from dotenv import load_dotenv

# ✅ Correct absolute imports for module execution
from backend.agents.base import AgentConfig
from backend.agents.job_fetcher import JobFetcherAgent
from backend.agents.job_matcher import JobMatcherAgent
from backend.agents.resume_agent import ResumeAgent
from backend.agents.github_ingestion_agent import GitHubIngestionAgent


class Orchestrator:
    """
    Runs all agents on independent schedules.
    Each agent runs in its own thread using its own state file.
    """

    def __init__(self):
        load_dotenv()

        backend_url = "http://127.0.0.1:8000"

        # --------------------------------------------
        # GitHub agent credentials
        # --------------------------------------------
        github_username = os.getenv("GITHUB_USERNAME")
        github_token = os.getenv("GITHUB_TOKEN")

        if not github_username:
            raise ValueError("❌ Missing GITHUB_USERNAME in .env")
        if not github_token:
            raise ValueError("❌ Missing GITHUB_TOKEN in .env")

        # --------------------------------------------
        # Initialize agents — each with its own state!
        # --------------------------------------------
        self.agents = {
            "job_fetcher": {
                "instance": JobFetcherAgent(
                    AgentConfig(
                        backend_url=backend_url,
                        state_path="state_job_fetcher.json",
                        sleep_interval=5
                    )
                ),
                "interval": 60 * 60 * 2,  # 2 hours
                "last_run": 0
            },

            "job_matcher": {
                "instance": JobMatcherAgent(
                    AgentConfig(
                        backend_url=backend_url,
                        state_path="state_job_matcher.json",
                        sleep_interval=5
                    )
                ),
                "interval": 60 * 10,  # 10 minutes
                "last_run": 0
            },

            "resume_agent": {
                "instance": ResumeAgent(
                    AgentConfig(
                        backend_url=backend_url,
                        state_path="state_resume_agent.json",
                        sleep_interval=5
                    )
                ),
                "interval": 60 * 10,  # 10 minutes
                "last_run": 0
            },

            "github_ingestion": {
                "instance": GitHubIngestionAgent(
                    config=AgentConfig(
                        backend_url=backend_url,
                        state_path="state_github_ingestion.json",
                        sleep_interval=5
                    ),
                    github_username=github_username,
                    github_token=github_token
                ),
                "interval": 60 * 60 * 6,  # 6 hours
                "last_run": 0
            },
        }

    # -------------------------------------------------------------
    # Run an agent safely in its own thread
    # -------------------------------------------------------------
    def run_agent_once(self, name: str, agent_obj):
        try:
            agent_obj.step()
        except Exception as e:
            print(f"[ERROR] Agent {name} crashed: {e}")
            traceback.print_exc()

    # -------------------------------------------------------------
    # Main orchestrator loop
    # -------------------------------------------------------------
    def start(self):
        print("🚀 Alfred Orchestrator started.")

        while True:
            now = time.time()

            for name, cfg in self.agents.items():
                agent = cfg["instance"]
                interval = cfg["interval"]
                last_run = cfg["last_run"]

                # Time to run?
                if now - last_run >= interval:
                    print(f"[Orchestrator] ▶ Running {name}...")

                    thread = threading.Thread(
                        target=self.run_agent_once,
                        args=(name, agent),
                        daemon=True
                    )
                    thread.start()

                    cfg["last_run"] = now

            time.sleep(5)  # Prevent CPU overuse


if __name__ == "__main__":
    orchestrator = Orchestrator()
    orchestrator.start()

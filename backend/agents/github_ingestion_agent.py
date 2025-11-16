import hashlib
import requests
from typing import Dict, Any, Optional, List

from .base import BaseAgent, AgentConfig
from dotenv import load_dotenv
import os

class GitHubIngestionAgent(BaseAgent):
    """
    Scans a GitHub user's repositories and generates:
      - Project summaries
      - Technology tags
      - Contribution highlights
    Then ingests them into Alfred's knowledge base as new artifacts.
    """

    GITHUB_API = "https://api.github.com"

    def __init__(self, config: AgentConfig, github_username: str, github_token: Optional[str] = None):
        super().__init__("GitHubIngestionAgent", config)

        self.github_username = github_username
        self.github_token = github_token

        if "ingested_repos" not in self.state:
            self.state["ingested_repos"] = []

    # ----------------------------------------------------------------------
    # GitHub API Helpers
    # ----------------------------------------------------------------------
    def github_headers(self) -> Dict[str, str]:
        """Authorization header if a token is provided."""
        headers = {
            "Accept": "application/vnd.github+json"
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    def fetch_repos(self) -> Optional[List[Dict[str, Any]]]:
        """Retrieve list of public repos for the given GitHub username."""
        url = f"{self.GITHUB_API}/users/{self.github_username}/repos?per_page=100"
        try:
            resp = requests.get(url, headers=self.github_headers(), timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.logger.error(f"GitHub repo fetch failed: {e}")
            return None

    def already_ingested(self, repo: Dict[str, Any]) -> bool:
        """Avoid duplicates using repo name + last updated timestamp."""
        fingerprint = f"{repo.get('name')}::{repo.get('updated_at')}"
        return fingerprint in self.state["ingested_repos"]

    def mark_ingested(self, repo: Dict[str, Any]):
        fingerprint = f"{repo.get('name')}::{repo.get('updated_at')}"
        self.state["ingested_repos"].append(fingerprint)

    # ----------------------------------------------------------------------
    # Summarization + Ingestion
    # ----------------------------------------------------------------------
    def summarize_repo(self, repo: Dict[str, Any]) -> Optional[str]:
        """
        Ask the backend's generator model to create a structured project summary.
        This ensures consistent, factual artifact content.
        """
        description = repo.get("description") or "No description provided."
        name = repo.get("name", "Unnamed Repository")
        languages_url = repo.get("languages_url")

        # Fetch languages
        languages = []
        try:
            resp = requests.get(languages_url, headers=self.github_headers(), timeout=30)
            resp.raise_for_status()
            lang_data = resp.json()
            languages = list(lang_data.keys())
        except Exception:
            pass

        prompt = f"""
You are creating a structured summary of a GitHub project for use in job applications.

Repository: {name}
Description: {description}
Languages: {', '.join(languages)}

Produce:
- Project Overview (2–3 sentences)
- Key Technologies (list)
- key software development life cycle contributions
- If Data Science/ML, mention datasets/models used
"""

        payload = {"prompt": prompt}
        resp = self.api_post("/generate/github_summary", payload)

        if resp is None:
            return None

        return resp.get("summary_text")

    def ingest_summary(self, repo_name: str, summary_text: str) -> Optional[Dict]:
        """
        Store the project summary in Alfred's knowledge base as an artifact.
        """
        payload = {
            "name": f"GitHub Project: {repo_name}",
            "content": summary_text,
            "source": "github",
            "metadata": {
                "repo_name": repo_name
            }
        }
        return self.api_post("/artifacts/ingest_raw", payload)

    # ----------------------------------------------------------------------
    # Main Step
    # ----------------------------------------------------------------------
    def step(self):
        self.logger.info("Checking GitHub for new repositories...")

        repos = self.fetch_repos()
        if repos is None:
            self.logger.error("No repositories fetched.")
            return

        for repo in repos:
            name = repo.get("name")
            if self.already_ingested(repo):
                continue

            self.logger.info(f"Ingesting GitHub repository: {name}")

            summary = self.summarize_repo(repo)
            if summary is None:
                self.logger.error(f"Summary generation failed for {name}")
                continue

            self.logger.info(f"Summary generated for {name}")

            resp = self.ingest_summary(name, summary)
            if resp is None:
                self.logger.error(f"Artifact ingestion failed for {name}")
                continue

            self.mark_ingested(repo)
            self.logger.info(f"Ingested GitHub project '{name}' as artifact ID {resp.get('id')}")

        self.logger.info("GitHub ingestion step complete.")
# ---------------------------------------------------------
# Manual Launcher
# ---------------------------------------------------------
if __name__ == "__main__":
    import os
    from backend.agents.base import AgentConfig

    # Load env vars
    from dotenv import load_dotenv
    load_dotenv()

    api_base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    github_username = os.getenv("GITHUB_USERNAME")
    github_token = os.getenv("GITHUB_TOKEN")

    if not github_username:
        raise ValueError("❌ Missing GITHUB_USERNAME in .env")

    # Shared config
    config = AgentConfig(
        backend_url=api_base,
        state_path="github_ingestion_state.json",
        sleep_interval=10
    )

    agent = GitHubIngestionAgent(
        config=config,
        github_username=github_username,
        github_token=github_token
    )

    print("➡️ GitHubIngestionAgent starting...")
    agent.run()

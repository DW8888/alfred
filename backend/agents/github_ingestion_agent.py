import base64
import json
import requests
from typing import Dict, Any, Optional, List
import os
import re

from .base import BaseAgent, AgentConfig


class GitHubIngestionAgent(BaseAgent):
    """
    Upgraded agent that:
      - Reads README files
      - Reads code files (.py, .js, .java, .r, etc.)
      - Reads Jupyter notebooks (.ipynb)
      - Stores *all file contents* into RAG as artifacts
      - Skips PDFs and binary files
    """

    GITHUB_API = "https://api.github.com"

    ALLOWED_EXTENSIONS = {
        ".md", ".txt", ".py", ".ipynb", ".r", ".js", ".ts",
        ".json", ".yaml", ".yml", ".toml", ".java", ".cpp",".pdf"
    }

    IGNORED_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".svg",
        ".zip", ".exe", ".dll", ".bin"
    }

    def __init__(self, config: AgentConfig, github_username: str, github_token: Optional[str] = None):
        super().__init__("GitHubIngestionAgent", config)

        self.github_username = github_username
        self.github_token = github_token

        if "ingested_repos" not in self.state:
            self.state["ingested_repos"] = []

    # ------------------------------------------------------
    # GitHub API helpers
    # ------------------------------------------------------
    def headers(self):
        h = {"Accept": "application/vnd.github+json"}
        if self.github_token:
            h["Authorization"] = f"Bearer {self.github_token}"
        return h

    def fetch_repos(self):
        url = f"{self.GITHUB_API}/users/{self.github_username}/repos?per_page=100"
        try:
            resp = requests.get(url, headers=self.headers(), timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.logger.error(f"GitHub repo fetch failed: {e}")
            return None

    def fetch_repo_tree(self, repo_name: str) -> Optional[List[Dict]]:
        """Fetch recursive file tree of the repo."""
        url = f"{self.GITHUB_API}/repos/{self.github_username}/{repo_name}/git/trees/master?recursive=1"
        try:
            resp = requests.get(url, headers=self.headers(), timeout=30)
            resp.raise_for_status()
            return resp.json().get("tree", [])
        except Exception as e:
            self.logger.error(f"Failed to fetch file tree for {repo_name}: {e}")
            return None

    # ------------------------------------------------------
    # Content Downloading
    # ------------------------------------------------------
    def download_file(self, repo: str, path: str) -> Optional[str]:
        """Download the raw file content."""
        raw_url = f"https://raw.githubusercontent.com/{self.github_username}/{repo}/master/{path}"
        try:
            resp = requests.get(raw_url, headers=self.headers(), timeout=30)
            if resp.status_code != 200:
                return None
            return resp.text
        except Exception:
            return None

    def parse_ipynb(self, raw: str) -> str:
        """Extract readable content from .ipynb file."""
        try:
            data = json.loads(raw)
            text_chunks = []

            for cell in data.get("cells", []):
                if cell.get("cell_type") == "markdown":
                    text_chunks.append("\n".join(cell.get("source", [])))
                elif cell.get("cell_type") == "code":
                    text_chunks.append("\n```python\n" + "".join(cell.get("source", [])) + "\n```")

            return "\n\n".join(text_chunks)

        except Exception:
            return ""

    # ------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------
    def ingest_file(self, repo: str, path: str, content: str):
        ext = os.path.splitext(path)[1].lower()

        payload = {
            "name": f"GitHub File: {repo}/{path}",
            "content": content,
            "source": "github_source_file",
            "metadata": {
                "repo": repo,
                "path": path,
                "extension": ext,
            }
        }

        return self.api_post("/artifacts/ingest_raw", payload)

    # ------------------------------------------------------
    # Main Loop
    # ------------------------------------------------------
    def step(self):
        self.logger.info("Checking GitHub for updated repositories...")

        repos = self.fetch_repos()
        if repos is None:
            return

        for repo in repos:
            repo_name = repo.get("name")
            updated_at = repo.get("updated_at")

            fingerprint = f"{repo_name}::{updated_at}"
            if fingerprint in self.state["ingested_repos"]:
                continue

            self.logger.info(f"📥 Ingesting repo: {repo_name}")

            tree = self.fetch_repo_tree(repo_name)
            if tree is None:
                continue

            for item in tree:
                if item.get("type") != "blob":
                    continue

                path = item["path"]
                ext = os.path.splitext(path)[1].lower()

                # skip ignored extensions
                if ext in self.IGNORED_EXTENSIONS:
                    continue

                # skip weird binary files
                if not any(path.endswith(a) for a in self.ALLOWED_EXTENSIONS):
                    continue

                raw = self.download_file(repo_name, path)
                if raw is None:
                    continue

                if ext == ".ipynb":
                    raw = self.parse_ipynb(raw)

                self.ingest_file(repo_name, path, raw)

            self.state["ingested_repos"].append(fingerprint)
            self.logger.info(f"✔ Completed ingestion for {repo_name}")

        self.logger.info("GitHub ingestion step complete.")

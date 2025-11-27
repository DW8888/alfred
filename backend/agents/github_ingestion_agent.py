import json
import requests
from typing import Dict, Any, Optional, List
import os
import re

from .base import BaseAgent, AgentConfig


class GitHubIngestionAgent(BaseAgent):
    """
    GitHub ingestion agent that:

      - Lists all repos for a GitHub user
      - Walks the file tree for each repo
      - For each allowed text/code file:
          * Downloads the content
          * Parses notebooks (.ipynb) into readable text
          * Calls /generate/github_summary to summarize the file
          * Stores the summary as an artifact via /artifacts/ingest_raw
      - Tracks per-file GitHub blob SHAs in state so that:
          * Unchanged files are skipped on subsequent runs
          * State is saved after each successfully ingested file
    """

    GITHUB_API = "https://api.github.com"

    # Text/code formats we care about
    ALLOWED_EXTENSIONS = {
        ".md", ".txt",
        ".py", ".ipynb", ".r",
        ".js", ".ts",
        ".json", ".yaml", ".yml", ".toml",
        ".java", ".cpp",
    }

    # Binary/media we ignore
    IGNORED_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".svg",
        ".zip", ".exe", ".dll", ".bin",
        ".mp3", ".mp4", ".mov", ".avi",
        ".pdf",
    }

    def __init__(self, config: AgentConfig, github_username: str, github_token: Optional[str] = None):
        super().__init__("GitHubIngestionAgent", config)
        self.github_username = github_username
        self.github_token = github_token

        # New state layout: per-repo, per-file SHA fingerprints
        # {
        #   "repos": {
        #       "RepoName": {
        #           "files": {
        #               "path/to/file.py": "blob_sha",
        #               ...
        #           }
        #       }
        #   }
        # }
        if "repos" not in self.state:
            self.state["repos"] = {}

        # Keep old key if it exists, but we don't rely on it anymore
        if "ingested_repos" not in self.state:
            self.state["ingested_repos"] = []

    # -------------------------------------------------------------------------
    # GitHub helpers
    # -------------------------------------------------------------------------
    def headers(self) -> Dict[str, str]:
        h = {"Accept": "application/vnd.github+json"}
        if self.github_token:
            h["Authorization"] = f"Bearer {self.github_token}"
        return h

    def fetch_repos(self) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.GITHUB_API}/users/{self.github_username}/repos?per_page=100"
        try:
            resp = requests.get(url, headers=self.headers(), timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.logger.error(f"GitHub repo fetch failed: {e}")
            return None

    def fetch_repo_tree(self, repo_name: str, branch: str) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.GITHUB_API}/repos/{self.github_username}/{repo_name}/git/trees/{branch}?recursive=1"
        try:
            resp = requests.get(url, headers=self.headers(), timeout=30)
            resp.raise_for_status()
            return resp.json().get("tree", [])
        except Exception as e:
            self.logger.error(f"Failed to fetch file tree for {repo_name}@{branch}: {e}")
            return None

    def download_file(self, repo: str, path: str, branch: str) -> Optional[str]:
        raw_url = f"https://raw.githubusercontent.com/{self.github_username}/{repo}/{branch}/{path}"
        try:
            resp = requests.get(raw_url, headers=self.headers(), timeout=30)
            if resp.status_code != 200:
                self.logger.debug(f"Skipping {repo}/{path}, HTTP {resp.status_code}")
                return None
            return resp.text
        except Exception as e:
            self.logger.error(f"Error downloading {repo}/{path}: {e}")
            return None

    # -------------------------------------------------------------------------
    # Notebook parsing
    # -------------------------------------------------------------------------
    def parse_ipynb(self, raw: str) -> str:
        """
        Extract markdown + code cells from a notebook into readable text.
        """
        try:
            data = json.loads(raw)
            text_chunks: List[str] = []

            for cell in data.get("cells", []):
                cell_type = cell.get("cell_type")
                source_lines = cell.get("source", [])

                if cell_type == "markdown":
                    text_chunks.append("".join(source_lines))
                elif cell_type == "code":
                    code = "".join(source_lines)
                    text_chunks.append(f"\n```python\n{code}\n```")

            return "\n\n".join(text_chunks).strip()
        except Exception as e:
            self.logger.error(f"Failed to parse ipynb: {e}")
            return ""

    # -------------------------------------------------------------------------
    # Technology extraction
    # -------------------------------------------------------------------------
    def extract_techs(self, path: str, content: str) -> List[str]:
        ext = os.path.splitext(path)[1].lower()
        techs: List[str] = []

        ext_map = {
            ".py": "python",
            ".ipynb": "python",
            ".r": "r",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".cpp": "cpp",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".md": "markdown",
        }
        if ext in ext_map:
            techs.append(ext_map[ext])

        patterns = {
            "fastapi": r"\bFastAPI\b",
            "flask": r"\bflask\b",
            "django": r"\bdjango\b",
            "pandas": r"\bpandas\b",
            "numpy": r"\bnumpy\b",
            "pytorch": r"\btorch\b",
            "tensorflow": r"\btensorflow\b|\bkeras\b",
            "react": r"\bReact\b",
            "node": r"\bexpress\b",
            "sql": r"\bSELECT\b\s+.*\bFROM\b",
            "docker": r"\bFROM\b\s+\w+",
        }
        for tech, pattern in patterns.items():
            if re.search(pattern, content, re.IGNORECASE):
                techs.append(tech)

        # dedupe, preserve order
        seen = set()
        out: List[str] = []
        for t in techs:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    # -------------------------------------------------------------------------
    # Summarization
    # -------------------------------------------------------------------------
    def summarize_file(self, repo: str, path: str, content: str) -> Optional[str]:
        # Cap content for prompt to avoid huge payloads
        snippet = content[:5000]

        prompt = f"""
You are generating a structured summary of a GitHub CODE FILE.

Repository: {repo}
File Path: {path}

Content:
{snippet}

Return:
- File purpose (2–3 sentences)
- Key functions/classes
- Technologies used
- How this file contributes to the larger project
"""

        resp = self.api_post("/generate/github_summary", {"prompt": prompt})
        if resp is None:
            return None
        return resp.get("summary_text")

    # -------------------------------------------------------------------------
    # Artifact ingestion
    # -------------------------------------------------------------------------
    def ingest_file(self, repo: str, path: str, summary: str, content: str):
        ext = os.path.splitext(path)[1].lower()
        techs = self.extract_techs(path, content)

        payload = {
            "name": f"GitHub File: {repo}/{path}",
            "content": summary,
            "source": "github_source_file",
            "metadata": {
                "repo": repo,
                "path": path,
                "extension": ext,
                "technologies": techs,
                # Optionally keep a short excerpt of the raw content if you want
                "excerpt": content[:1000],
            },
        }

        return self.api_post("/artifacts/ingest_raw", payload)

    # -------------------------------------------------------------------------
    # Main step – SHA-based file-level fingerprints
    # -------------------------------------------------------------------------
    def step(self):
        self.logger.info("Checking GitHub for repositories (SHA-based incremental)...")

        if not self.github_username:
            self.logger.error("No GitHub username configured; aborting.")
            return

        repos = self.fetch_repos()
        if not repos:
            self.logger.warning("No repositories fetched from GitHub.")
            return

        repos_state = self.state.setdefault("repos", {})

        for repo in repos:
            repo_name = repo.get("name")
            if not repo_name:
                continue

            default_branch = repo.get("default_branch", "master") or "master"

            print(f">>>[INGEST] Repo: {repo_name} (branch={default_branch})")
            self.logger.info(f"Ingesting repo: {repo_name} (branch={default_branch})")

            # Get or init state for this repo
            repo_state = repos_state.setdefault(repo_name, {})
            files_state: Dict[str, str] = repo_state.setdefault("files", {})

            tree = self.fetch_repo_tree(repo_name, default_branch)
            if tree is None:
                print(f"====>> Skipping {repo_name}, no tree fetched.")
                continue

            seen_paths = set()

            for item in tree:
                if item.get("type") != "blob":
                    continue

                path = item.get("path")
                sha = item.get("sha")
                if not path or not sha:
                    continue

                ext = os.path.splitext(path)[1].lower()
                if ext in self.IGNORED_EXTENSIONS:
                    continue
                if ext not in self.ALLOWED_EXTENSIONS:
                    continue

                seen_paths.add(path)

                # Skip unchanged files by SHA
                previous_sha = files_state.get(path)
                if previous_sha == sha:
                    # unchanged since last ingestion
                    print(f"===>>> Skipping unchanged file: {path}")
                    continue

                print(f">>>> Processing file: {path}")

                raw = self.download_file(repo_name, path, default_branch)
                if raw is None:
                    print(f"---!! Failed to download {path}")
                    continue

                if ext == ".ipynb":
                    content = self.parse_ipynb(raw)
                    if not content:
                        print(f"---!! Parsed notebook empty, skipping {path}")
                        continue
                else:
                    content = raw

                if not content.strip():
                    print(f"---!! Empty content, skipping {path}")
                    continue

                summary = self.summarize_file(repo_name, path, content)
                if summary is None:
                    print(f"---!! Summary generation failed for {path}")
                    continue

                resp = self.ingest_file(repo_name, path, summary, content)
                if resp is None:
                    print(f"---!! Artifact ingestion failed for {path}")
                    continue

                artifact_id = resp.get("id")
                print(f"--OK-- Ingested file as artifact {artifact_id}")

                # Update SHA fingerprint and save state immediately
                files_state[path] = sha
                try:
                    self._save_state()
                except Exception as e:
                    self.logger.error(f"Failed to save state after {repo_name}/{path}: {e}")

            # Optional: remove fingerprints for files that no longer exist
            removed_paths = [p for p in files_state.keys() if p not in seen_paths]
            if removed_paths:
                for p in removed_paths:
                    del files_state[p]
                try:
                    self._save_state()
                except Exception as e:
                    self.logger.error(f"Failed to save state after pruning {repo_name}: {e}")

            print(f"--[DONE]-- Completed repo: {repo_name}")

        print("GitHub ingestion step complete.")


# -------------------------------------------------------------------------
# Manual launcher – single run, state saved after each file
# -------------------------------------------------------------------------
if __name__ == "__main__":
    from dotenv import load_dotenv
    from pathlib import Path

    load_dotenv()

    api_base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    github_username = os.getenv("GITHUB_USERNAME")
    github_token = os.getenv("GITHUB_TOKEN")

    if not github_username:
        raise ValueError("--xXx-- Missing GITHUB_USERNAME in .env")

    # State file at project root: <project_root>/github_ingestion_state.json
    project_root = Path(__file__).resolve().parents[2]
    state_file = project_root / "github_ingestion_state.json"

    # Ensure directory exists (project root should already exist)
    config = AgentConfig(
        backend_url=api_base,
        state_path=str(state_file),
        sleep_interval=10,  # kept for compatibility, not used in one-shot mode
    )

    agent = GitHubIngestionAgent(
        config=config,
        github_username=github_username,
        github_token=github_token,
    )

    print("-->>>-->>> GitHubIngestionAgent starting...")
    print(f"   State file: {state_file}")

    agent.step()  # step() saves state after each file

    print("✔✔✔ Done ✔✔✔")

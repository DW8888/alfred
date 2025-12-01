from dotenv import load_dotenv
load_dotenv()
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


import requests
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

class AgentConfig:
    """
    Holds configuration shared by all agents.
    """
    def __init__(
        self,
        backend_url: str = "http://127.0.0.1:8000",
        state_path: str = "agent_state.json",
        sleep_interval: int = 5
    ):
        self.backend_url = backend_url
        self.state_path = state_path
        self.sleep_interval = sleep_interval


class BaseAgent(ABC):
    """
    Base class for all agents.
    Provides:
      - Logging
      - Persistent state
      - HTTP client for backend
      - Lifecycle: run → step()
    """

    def __init__(self, name: str, config: AgentConfig):
        self.name = name
        self.config = config
        self.state = self._load_state()

        # Setup logger
        self.logger = logging.getLogger(self.name)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.logger.setLevel(logging.INFO)
        self.logger.info(f"{self.name} initialized.")

    # ----------------------------------------------------------------------
    # Persistent State Handling
    # ----------------------------------------------------------------------
    def _load_state(self) -> Dict[str, Any]:
        """
        Load agent state from file.
        """
        if not os.path.exists(self.config.state_path):
            return {}
        try:
            with open(self.config.state_path, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_state(self):
        """
        Save agent state to file.
        """
        try:
            with open(self.config.state_path, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save state: {e}")

    # ----------------------------------------------------------------------
    # Backend API Helper
    # ----------------------------------------------------------------------
    def api_post(self, path: str, payload: Dict[str, Any]) -> Optional[Dict]:
        """
        POST request to the FastAPI backend.
        """
        try:
            url = f"{self.config.backend_url}{path}"
            resp = requests.post(url, json=payload, timeout=180)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.logger.error(f"POST {path} failed: {e}")
            return None

    def api_get(self, path: str) -> Optional[Dict]:
        """
        GET request to the FastAPI backend.
        """
        try:
            url = f"{self.config.backend_url}{path}"
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.logger.error(f"GET {path} failed: {e}")
            return None

    # ----------------------------------------------------------------------
    # Agent Lifecycle
    # ----------------------------------------------------------------------
    def run(self):
        """
        Main loop. Agent repeatedly calls step(), saves state, and sleeps.
        """
        self.logger.info(f"{self.name} starting run loop.")

        while True:
            try:
                self.step()
                self._save_state()
            except Exception as e:
                self.logger.error(f"Error in step(): {e}")

            time.sleep(self.config.sleep_interval)

    @abstractmethod
    def step(self):
        """
        Must be implemented by child agents.
        """
        pass

import json
import os
from functools import lru_cache
from typing import Any, Dict


PROFILE_PATH = os.path.join(os.path.dirname(__file__), "profile.json")


@lru_cache(maxsize=1)
def load_profile() -> Dict[str, Any]:
    if not os.path.exists(PROFILE_PATH):
        raise FileNotFoundError(
            f"Profile file not found at {PROFILE_PATH}. "
            "Create it from profile_template.json."
        )
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

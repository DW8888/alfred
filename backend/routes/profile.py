import json
import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.profile import utils as profile_utils
from backend.profile.utils import load_profile, PROFILE_PATH


PREFERENCES_PATH = os.path.join(os.path.dirname(PROFILE_PATH), "preferences.json")

router = APIRouter(prefix="/profile", tags=["Profile"])


class ProfilePayload(BaseModel):
    data: Dict[str, Any]


class PreferencesPayload(BaseModel):
    target_title: str | None = None
    location: str | None = None
    results_per_page: int | None = None
    max_pages: int | None = None


def _ensure_preferences() -> Dict[str, Any]:
    if not os.path.exists(PREFERENCES_PATH):
        default = {
            "target_title": "",
            "location": "",
            "results_per_page": 20,
            "max_pages": 3,
        }
        with open(PREFERENCES_PATH, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
        return default
    with open(PREFERENCES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/")
def get_profile():
    try:
        return load_profile()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/")
def update_profile(payload: Dict[str, Any]):
    try:
        with open(PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        profile_utils.load_profile.cache_clear()
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/preferences")
def get_preferences():
    prefs = _ensure_preferences()
    return prefs


@router.put("/preferences")
def update_preferences(payload: PreferencesPayload):
    prefs = _ensure_preferences()
    if payload.target_title is not None:
        prefs["target_title"] = payload.target_title
    if payload.location is not None:
        prefs["location"] = payload.location
    if payload.results_per_page is not None:
        if payload.results_per_page <= 0:
            raise HTTPException(status_code=400, detail="results_per_page must be positive")
        prefs["results_per_page"] = payload.results_per_page
    if payload.max_pages is not None:
        if payload.max_pages <= 0:
            raise HTTPException(status_code=400, detail="max_pages must be positive")
        prefs["max_pages"] = payload.max_pages
    with open(PREFERENCES_PATH, "w", encoding="utf-8") as f:
        json.dump(prefs, f, indent=2)
    return {"status": "ok", "preferences": prefs}

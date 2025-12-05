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


def _ensure_preferences() -> Dict[str, Any]:
    if not os.path.exists(PREFERENCES_PATH):
        default = {"target_title": "", "location": ""}
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
    with open(PREFERENCES_PATH, "w", encoding="utf-8") as f:
        json.dump(prefs, f, indent=2)
    return {"status": "ok", "preferences": prefs}

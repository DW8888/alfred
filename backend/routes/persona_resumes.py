from __future__ import annotations

import json
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Query


router = APIRouter(prefix="/persona_resumes", tags=["Persona Resumes"])

PROMPT_RUNS_DIR = (
    Path(__file__)
    .resolve()
    .parents[2]
    / "model"
    / "experimentation"
    / "outputs"
    / "prompt_runs"
)


def _load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500, detail=f"Corrupted JSON in {path.name}: {exc}"
        ) from exc


@router.get("/")
def list_persona_resumes(
    variant: str | None = Query(default=None, description="Optional persona variant filter (e.g. P0)"),
    limit: int | None = Query(default=None, ge=1, le=10000),
) -> List[dict]:
    """Return summaries of generated persona resumes stored on disk."""
    if not PROMPT_RUNS_DIR.exists():
        return []

    requested = variant.upper() if variant else None
    entries: List[dict] = []

    for persona_dir in sorted(PROMPT_RUNS_DIR.iterdir()):
        if not persona_dir.is_dir():
            continue
        persona_name = persona_dir.name
        if requested and persona_name.upper() != requested:
            continue
        for file_path in sorted(persona_dir.glob("job_*.json")):
            data = _load_json(file_path)
            reasoning = str(data.get("reasoning", "")).strip()
            entries.append(
                {
                    "variant": persona_name,
                    "job_id": int(data.get("job_id", 0)),
                    "artifact_id": data.get("artifact_id"),
                    "reasoning_preview": reasoning[:180] + ("..." if len(reasoning) > 180 else ""),
                    "filename": file_path.name,
                    "updated_at": file_path.stat().st_mtime,
                }
            )

    entries.sort(key=lambda item: (item["variant"], item["job_id"]))
    if limit:
        return entries[:limit]
    return entries


@router.get("/{variant}/{job_id}")
def get_persona_resume(variant: str, job_id: int) -> dict:
    """Return the complete resume JSON for a persona/job pair."""
    persona_dir = PROMPT_RUNS_DIR / variant
    if not persona_dir.exists():
        raise HTTPException(status_code=404, detail=f"Variant '{variant}' not found")

    file_path = persona_dir / f"job_{job_id}.json"
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No resume file for variant '{variant}' and job_id '{job_id}'",
        )

    data = _load_json(file_path)
    data["variant"] = variant
    data["filename"] = file_path.name
    data["updated_at"] = file_path.stat().st_mtime
    return data

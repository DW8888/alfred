from pydantic import BaseModel
from typing import Optional
from datetime import datetime



# ------------------------------------------------------
# Base shared fields
# ------------------------------------------------------
class JobBase(BaseModel):
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    source_url: str

# ------------------------------------------------------
# Schema for creating a job (incoming POST)
# ------------------------------------------------------
class JobCreate(JobBase):
    pass

# ------------------------------------------------------
# Schema for reading a job (outgoing response)
# ------------------------------------------------------
class JobRead(JobBase):
    id: int
    created_at: datetime | None = None
    match_score: float | None = None

    model_config = {
        "from_attributes": True
    }

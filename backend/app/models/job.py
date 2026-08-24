from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class JobCreate(BaseModel):
    company: str
    title: str
    url: Optional[str] = None
    location: Optional[str] = None
    salary: Optional[str] = None
    status: str = "wishlist"
    match_score: Optional[int] = 85
    job_description: Optional[str] = None
    analysis_data: Optional[Dict[str, Any]] = None
    tailored_profile: Optional[str] = "technical_pm"
    custom_summary: Optional[str] = None
    selected_bullets: Optional[List[str]] = None
    notes: Optional[str] = None

class JobUpdate(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    location: Optional[str] = None
    salary: Optional[str] = None
    status: Optional[str] = None
    match_score: Optional[int] = None
    job_description: Optional[str] = None
    analysis_data: Optional[Dict[str, Any]] = None
    tailored_profile: Optional[str] = None
    custom_summary: Optional[str] = None
    selected_bullets: Optional[List[str]] = None
    notes: Optional[str] = None
    cv_pdf_filename: Optional[str] = None
    is_archived: Optional[int] = None
    interest_rating: Optional[int] = None

class SnapshotCreate(BaseModel):
    stage: str = "applied"
    custom_summary: Optional[str] = None
    selected_bullets: Optional[List[str]] = None
    job_description: Optional[str] = None

class RatingRequest(BaseModel):
    rating: int  # 1 for thumbs up, -1 for thumbs down, 0 for clear

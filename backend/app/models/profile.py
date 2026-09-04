from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class BulletItem(BaseModel):
    id: str
    text: str
    category: str = "General"
    tags: List[str] = []
    default: bool = True

class ExperienceItem(BaseModel):
    company: str
    role: str
    location: Optional[str] = None
    dates: str
    bullets: List[BulletItem] = []

class EducationItem(BaseModel):
    institution: str
    degree: str
    honors: Optional[str] = None
    gpa: Optional[str] = None
    dates: str
    details: Optional[str] = None

class ArchetypeProfile(BaseModel):
    title: str
    summary: str
    active_tags: List[str] = []

class CareerPreferences(BaseModel):
    target_roles: List[str] = ["Software Engineer", "Technical Program Manager", "Data Engineer"]
    target_locations: List[str] = ["Israel", "United States", "Remote"]
    target_seniority: List[str] = ["Mid-Level", "Senior", "Lead", "Staff"]
    include_linkedin: bool = True
    remote_only: bool = False
    min_salary_usd: Optional[int] = 0

class CandidateProfile(BaseModel):
    id: Optional[int] = None
    is_active: bool = True
    is_onboarded: bool = False
    full_name: str = ""
    email: str = ""
    phone: Optional[str] = None
    location: Optional[str] = None
    citizenship: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    tagline: Optional[str] = None
    archetypes: Dict[str, ArchetypeProfile] = {}
    experience: List[ExperienceItem] = []
    education: List[EducationItem] = []
    skills: Dict[str, List[str]] = {}
    preferences: CareerPreferences = CareerPreferences()

class ProfileUpdateRequest(BaseModel):
    is_onboarded: Optional[bool] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    citizenship: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    tagline: Optional[str] = None
    archetypes: Optional[Dict[str, ArchetypeProfile]] = None
    experience: Optional[List[ExperienceItem]] = None
    education: Optional[List[EducationItem]] = None
    skills: Optional[Dict[str, List[str]]] = None
    preferences: Optional[CareerPreferences] = None

class TextIngestRequest(BaseModel):
    raw_text: str

class CommitProfileRequest(BaseModel):
    profile_data: Dict[str, Any]


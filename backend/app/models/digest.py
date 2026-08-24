from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class DigestQuery(BaseModel):
    query: Optional[str] = None
    region: Optional[str] = "all"
    category: Optional[str] = "all"
    role_family: Optional[str] = "all"
    yoe: Optional[str] = "all"
    min_match: Optional[int] = 0
    sort_by: Optional[str] = "match_desc"
    show_archived: Optional[bool] = False
    interest: Optional[str] = "all"

class CompanyCreate(BaseModel):
    name: str
    industry: Optional[str] = None
    careers_url: Optional[str] = None
    priority: str = "high"
    notes: Optional[str] = None
    region: Optional[str] = "Global"
    category: Optional[str] = "Tech"

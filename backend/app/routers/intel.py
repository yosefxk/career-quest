import json
from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter, HTTPException
from app.core.database import get_db
from app.engines.job_analyzer import (
    extract_job_text_from_url,
    analyze_job_fit,
    generate_recruiter_inmails,
    generate_company_intel,
    generate_role_mock_interview
)

router = APIRouter(prefix="/api/v1", tags=["intel"])

class AnalyzeRequest(BaseModel):
    url: Optional[str] = None
    job_text: Optional[str] = None

def get_active_profile_summary():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM candidate_profiles WHERE is_active = 1 LIMIT 1")
    cand_row = cursor.fetchone()
    conn.close()
    if not cand_row:
        return {"full_name": "Candidate", "tagline": "Technical Professional"}
    return {
        "full_name": cand_row["full_name"],
        "tagline": cand_row["tagline"],
        "archetypes": json.loads(cand_row["archetypes_json"] or "{}"),
        "skills": json.loads(cand_row["skills_json"] or "{}")
    }

@router.post("/analyze")
def analyze_job_url(req: AnalyzeRequest):
    extracted_text = req.job_text or ""
    page_title = ""
    cleaned_url = req.url or ""
    
    if req.url and not extracted_text:
        extracted_text, page_title, cleaned_url = extract_job_text_from_url(req.url)
        
    cand_profile = get_active_profile_summary()
    analysis = analyze_job_fit(extracted_text, cand_profile, url=cleaned_url)
    
    return {
        "extracted_text": extracted_text[:4000],
        "analysis": analysis
    }

@router.post("/jobs/{job_id}/inmail")
def get_job_inmail_variants(job_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    job_row = cursor.fetchone()
    conn.close()
    if not job_row:
        raise HTTPException(status_code=404, detail="Job not found")
        
    cand_profile = get_active_profile_summary()
    return generate_recruiter_inmails(
        company=job_row["company"],
        title=job_row["title"],
        job_description=job_row["job_description"] or "",
        candidate_profile=cand_profile
    )

@router.post("/jobs/{job_id}/company-intel")
def get_job_company_intel(job_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    job_row = cursor.fetchone()
    conn.close()
    if not job_row:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return generate_company_intel(
        company=job_row["company"],
        title=job_row["title"],
        job_description=job_row["job_description"] or ""
    )

@router.post("/jobs/{job_id}/mock-interview")
def get_job_mock_interview(job_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    job_row = cursor.fetchone()
    conn.close()
    if not job_row:
        raise HTTPException(status_code=404, detail="Job not found")
        
    cand_profile = get_active_profile_summary()
    return generate_role_mock_interview(
        company=job_row["company"],
        title=job_row["title"],
        job_description=job_row["job_description"] or "",
        candidate_profile=cand_profile
    )

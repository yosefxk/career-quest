import json
from fastapi import APIRouter, HTTPException
from app.core.database import get_db
from app.engines.cv_renderer import render_cv_html
from app.engines.job_analyzer import audit_ats_compliance

router = APIRouter(prefix="/api/v1", tags=["ats"])

@router.post("/jobs/{job_id}/ats-audit")
def run_job_ats_audit(job_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    job_row = cursor.fetchone()
    if not job_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")
        
    cursor.execute("SELECT * FROM candidate_profiles WHERE is_active = 1 LIMIT 1")
    cand_row = cursor.fetchone()
    conn.close()
    
    if not cand_row:
        raise HTTPException(status_code=400, detail="No active candidate profile")
        
    profile_data = {
        "full_name": cand_row["full_name"],
        "email": cand_row["email"],
        "phone": cand_row["phone"],
        "location": cand_row["location"],
        "citizenship": cand_row["citizenship"],
        "linkedin_url": cand_row["linkedin_url"],
        "github_url": cand_row["github_url"],
        "portfolio_url": cand_row["portfolio_url"],
        "tagline": cand_row["tagline"],
        "archetypes": json.loads(cand_row["archetypes_json"] or "{}"),
        "experience": json.loads(cand_row["experience_json"] or "[]"),
        "education": json.loads(cand_row["education_json"] or "[]"),
        "skills": json.loads(cand_row["skills_json"] or "{}")
    }
    
    selected_bullets = json.loads(job_row["selected_bullets_json"]) if job_row["selected_bullets_json"] else None
    html = render_cv_html(profile_data, custom_summary=job_row["custom_summary"], selected_bullet_ids=selected_bullets)
    
    audit = audit_ats_compliance(html, profile_data, job_description=job_row["job_description"])
    return audit

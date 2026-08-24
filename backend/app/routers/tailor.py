import json
import os
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from app.core.config import settings
from app.core.database import get_db
from app.engines.cv_renderer import render_cv_html, generate_cv_markdown, generate_cv_pdf

router = APIRouter(prefix="/api/v1", tags=["tailor"])

class PreviewRequest(BaseModel):
    company: Optional[str] = "Company"
    title: Optional[str] = "Title"
    profile_name: Optional[str] = "technical_pm"
    custom_summary: Optional[str] = None
    selected_bullets: Optional[List[str]] = None

class GenerateRequest(BaseModel):
    job_id: Optional[int] = None
    company: str
    title: str
    profile_name: Optional[str] = "technical_pm"
    custom_summary: Optional[str] = None
    selected_bullets: Optional[List[str]] = None

def get_active_profile_dict():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM candidate_profiles WHERE is_active = 1 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {
            "full_name": "Candidate Name",
            "email": "candidate@example.com",
            "phone": "+1 555-0100",
            "location": "Global / Remote",
            "skills": {},
            "experience": [],
            "education": []
        }
    return {
        "full_name": row["full_name"],
        "email": row["email"],
        "phone": row["phone"],
        "location": row["location"],
        "citizenship": row["citizenship"],
        "linkedin_url": row["linkedin_url"],
        "github_url": row["github_url"],
        "portfolio_url": row["portfolio_url"],
        "tagline": row["tagline"],
        "archetypes": json.loads(row["archetypes_json"] or "{}"),
        "experience": json.loads(row["experience_json"] or "[]"),
        "education": json.loads(row["education_json"] or "[]"),
        "skills": json.loads(row["skills_json"] or "{}")
    }

@router.post("/cv/preview", response_class=HTMLResponse)
def preview_cv(req: PreviewRequest):
    profile_data = get_active_profile_dict()
    html = render_cv_html(
        profile_data=profile_data,
        custom_summary=req.custom_summary,
        selected_bullet_ids=req.selected_bullets
    )
    return HTMLResponse(content=html)

@router.post("/cv/generate")
def generate_cv(req: GenerateRequest):
    profile_data = get_active_profile_dict()
    cand_name = profile_data.get("full_name", "Resume")
    
    html = render_cv_html(
        profile_data=profile_data,
        custom_summary=req.custom_summary,
        selected_bullet_ids=req.selected_bullets
    )
    md = generate_cv_markdown(
        profile_data=profile_data,
        custom_summary=req.custom_summary,
        selected_bullet_ids=req.selected_bullets
    )
    
    import datetime
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    folder_name = f"{today_str}_{req.company}_{req.title}"
    pdf_rel_path = generate_cv_pdf(html, folder_name, candidate_name=cand_name, markdown_content=md)
    
    if req.job_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET cv_pdf_filename = ? WHERE id = ?", (pdf_rel_path, req.job_id))
        conn.commit()
        conn.close()
        
    return {"status": "generated", "filename": pdf_rel_path}

@router.get("/jobs/{job_id}/cv.pdf")
def get_job_cv_pdf(job_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
        
    profile_data = get_active_profile_dict()
    cand_name = profile_data.get("full_name", "Resume")
    
    rel_path = row["cv_pdf_filename"]
    if rel_path:
        full_path = Path(settings.cvs_path) / rel_path
        if full_path.exists():
            return FileResponse(path=str(full_path), media_type="application/pdf", filename=f"{cand_name}.pdf")
            
    # Compile on-the-fly if not generated yet
    selected_bullets = json.loads(row["selected_bullets_json"]) if row["selected_bullets_json"] else None
    html = render_cv_html(profile_data, custom_summary=row["custom_summary"], selected_bullet_ids=selected_bullets)
    md = generate_cv_markdown(profile_data, custom_summary=row["custom_summary"], selected_bullet_ids=selected_bullets)
    
    import datetime
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    folder_name = f"{today_str}_{row['company']}_{row['title']}"
    pdf_rel_path = generate_cv_pdf(html, folder_name, candidate_name=cand_name, markdown_content=md)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET cv_pdf_filename = ? WHERE id = ?", (pdf_rel_path, job_id))
    conn.commit()
    conn.close()
    
    full_path = Path(settings.cvs_path) / pdf_rel_path
    return FileResponse(path=str(full_path), media_type="application/pdf", filename=f"{cand_name}.pdf")

@router.get("/jobs/{job_id}/cv.md", response_class=PlainTextResponse)
def get_job_cv_markdown(job_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
        
    profile_data = get_active_profile_dict()
    selected_bullets = json.loads(row["selected_bullets_json"]) if row["selected_bullets_json"] else None
    md = generate_cv_markdown(profile_data, custom_summary=row["custom_summary"], selected_bullet_ids=selected_bullets)
    return PlainTextResponse(content=md)

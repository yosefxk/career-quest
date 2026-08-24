import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, UploadFile, File
from app.core.database import get_db
from app.models.profile import CandidateProfile, ProfileUpdateRequest
from app.engines.job_analyzer import parse_uploaded_resume

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])

def row_to_profile(row) -> CandidateProfile:
    return CandidateProfile(
        id=row["id"],
        is_active=bool(row["is_active"]),
        full_name=row["full_name"],
        email=row["email"],
        phone=row["phone"],
        location=row["location"],
        citizenship=row["citizenship"],
        linkedin_url=row["linkedin_url"],
        github_url=row["github_url"],
        portfolio_url=row["portfolio_url"],
        tagline=row["tagline"],
        archetypes=json.loads(row["archetypes_json"] or "{}"),
        experience=json.loads(row["experience_json"] or "[]"),
        education=json.loads(row["education_json"] or "[]"),
        skills=json.loads(row["skills_json"] or "{}")
    )

@router.get("", response_model=CandidateProfile)
def get_active_profile():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM candidate_profiles WHERE is_active = 1 ORDER BY id ASC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No active candidate profile found")
    return row_to_profile(row)

@router.put("", response_model=CandidateProfile)
def update_active_profile(update: ProfileUpdateRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM candidate_profiles WHERE is_active = 1 ORDER BY id ASC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Profile not found")
        
    profile_id = row["id"]
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    fields = []
    values = []
    
    if update.full_name is not None: fields.append("full_name = ?"); values.append(update.full_name)
    if update.email is not None: fields.append("email = ?"); values.append(update.email)
    if update.phone is not None: fields.append("phone = ?"); values.append(update.phone)
    if update.location is not None: fields.append("location = ?"); values.append(update.location)
    if update.citizenship is not None: fields.append("citizenship = ?"); values.append(update.citizenship)
    if update.linkedin_url is not None: fields.append("linkedin_url = ?"); values.append(update.linkedin_url)
    if update.github_url is not None: fields.append("github_url = ?"); values.append(update.github_url)
    if update.portfolio_url is not None: fields.append("portfolio_url = ?"); values.append(update.portfolio_url)
    if update.tagline is not None: fields.append("tagline = ?"); values.append(update.tagline)
    if update.archetypes is not None: fields.append("archetypes_json = ?"); values.append(json.dumps({k: v.dict() for k, v in update.archetypes.items()}))
    if update.experience is not None: fields.append("experience_json = ?"); values.append(json.dumps([e.dict() for e in update.experience]))
    if update.education is not None: fields.append("education_json = ?"); values.append(json.dumps([e.dict() for e in update.education]))
    if update.skills is not None: fields.append("skills_json = ?"); values.append(json.dumps(update.skills))
    
    if fields:
        fields.append("updated_at = ?")
        values.append(now_str)
        values.append(profile_id)
        cursor.execute(f"UPDATE candidate_profiles SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        
    cursor.execute("SELECT * FROM candidate_profiles WHERE id = ?", (profile_id,))
    updated_row = cursor.fetchone()
    conn.close()
    return row_to_profile(updated_row)

@router.post("/upload")
async def upload_and_parse_resume(file: UploadFile = File(...)):
    """
    Upload a resume file (PDF, TXT, MD) to automatically extract candidate details,
    experience bullets, education, and skills into the active profile.
    """
    content = await file.read()
    parsed = parse_uploaded_resume(content, file.filename)
    if not parsed:
        raise HTTPException(status_code=400, detail="Could not parse resume content with AI.")
        
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
    UPDATE candidate_profiles SET
        full_name = ?,
        email = ?,
        phone = ?,
        location = ?,
        citizenship = ?,
        linkedin_url = ?,
        github_url = ?,
        portfolio_url = ?,
        tagline = ?,
        archetypes_json = ?,
        experience_json = ?,
        education_json = ?,
        skills_json = ?,
        updated_at = ?
    WHERE is_active = 1
    """, (
        parsed.get("full_name", "Candidate Name"),
        parsed.get("email", "email@example.com"),
        parsed.get("phone", ""),
        parsed.get("location", ""),
        parsed.get("citizenship", ""),
        parsed.get("linkedin_url", ""),
        parsed.get("github_url", ""),
        parsed.get("portfolio_url", ""),
        parsed.get("tagline", ""),
        json.dumps(parsed.get("archetypes", {})),
        json.dumps(parsed.get("experience", [])),
        json.dumps(parsed.get("education", [])),
        json.dumps(parsed.get("skills", {})),
        now_str
    ))
    conn.commit()
    conn.close()
    return {"status": "success", "profile": parsed}

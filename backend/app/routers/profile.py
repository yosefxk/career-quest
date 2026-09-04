import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File
from app.core.database import get_db
from app.models.profile import CandidateProfile, ProfileUpdateRequest, CareerPreferences, TextIngestRequest, CommitProfileRequest
from app.engines.job_analyzer import parse_uploaded_resume, parse_raw_resume_text

BACKUPS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "backups"

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])

def row_to_profile(row) -> CandidateProfile:
    pref_data = {}
    if "preferences_json" in row.keys() and row["preferences_json"]:
        try:
            pref_data = json.loads(row["preferences_json"])
        except Exception:
            pref_data = {}
            
    is_onboarded_val = False
    if "is_onboarded" in row.keys():
        is_onboarded_val = bool(row["is_onboarded"])
            
    return CandidateProfile(
        id=row["id"],
        is_active=bool(row["is_active"]),
        is_onboarded=is_onboarded_val,
        full_name=row["full_name"] or "",
        email=row["email"] or "",
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
        skills=json.loads(row["skills_json"] or "{}"),
        preferences=CareerPreferences(**pref_data) if pref_data else CareerPreferences()
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
    
    if update.is_onboarded is not None: fields.append("is_onboarded = ?"); values.append(1 if update.is_onboarded else 0)
    if update.full_name is not None: fields.append("full_name = ?"); values.append(update.full_name)
    if update.email is not None: fields.append("email = ?"); values.append(update.email)
    if update.phone is not None: fields.append("phone = ?"); values.append(update.phone)
    if update.location is not None: fields.append("location = ?"); values.append(update.location)
    if update.citizenship is not None: fields.append("citizenship = ?"); values.append(update.citizenship)
    if update.linkedin_url is not None: fields.append("linkedin_url = ?"); values.append(update.linkedin_url)
    if update.github_url is not None: fields.append("github_url = ?"); values.append(update.github_url)
    if update.portfolio_url is not None: fields.append("portfolio_url = ?"); values.append(update.portfolio_url)
    if update.tagline is not None: fields.append("tagline = ?"); values.append(update.tagline)
    if update.archetypes is not None: fields.append("archetypes_json = ?"); values.append(json.dumps({k: v.model_dump() for k, v in update.archetypes.items()}))
    if update.experience is not None: fields.append("experience_json = ?"); values.append(json.dumps([e.model_dump() for e in update.experience]))
    if update.education is not None: fields.append("education_json = ?"); values.append(json.dumps([e.model_dump() for e in update.education]))
    if update.skills is not None: fields.append("skills_json = ?"); values.append(json.dumps(update.skills))
    if update.preferences is not None: fields.append("preferences_json = ?"); values.append(json.dumps(update.preferences.model_dump()))
    
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

def backup_profile_to_file() -> Optional[str]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM candidate_profiles WHERE is_active = 1 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"profile_backup_{timestamp}.json"
    dest_path = BACKUPS_DIR / backup_filename
    data = dict(row)
    with open(dest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return backup_filename

def list_profile_backups() -> List[Dict[str, Any]]:
    if not BACKUPS_DIR.exists():
        return []
    backups = []
    for f in sorted(BACKUPS_DIR.glob("profile_backup_*.json"), key=os.path.getmtime, reverse=True):
        stat = f.stat()
        backups.append({
            "filename": f.name,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        })
    return backups

def restore_profile_backup(filename: str) -> bool:
    safe_name = os.path.basename(filename)
    target = BACKUPS_DIR / safe_name
    if not target.exists():
        return False
    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
    backup_profile_to_file()
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
        preferences_json = ?,
        updated_at = ?
    WHERE is_active = 1
    """, (
        data.get("full_name"),
        data.get("email"),
        data.get("phone"),
        data.get("location"),
        data.get("citizenship"),
        data.get("linkedin_url"),
        data.get("github_url"),
        data.get("portfolio_url"),
        data.get("tagline"),
        data.get("archetypes_json", "{}"),
        data.get("experience_json", "[]"),
        data.get("education_json", "[]"),
        data.get("skills_json", "{}"),
        data.get("preferences_json", "{}"),
        now_str
    ))
    conn.commit()
    conn.close()
    return True

@router.post("/upload")
async def upload_and_parse_resume(file: UploadFile = File(...)):
    """
    Upload a resume file (PDF, DOCX, TXT, MD, YAML) to parse into structured candidate profile.
    """
    content = await file.read()
    parsed = parse_uploaded_resume(content, file.filename)
    if not parsed:
        raise HTTPException(status_code=400, detail="Could not parse resume content with AI.")
        
    return {
        "status": "success",
        "filename": file.filename,
        "extracted_chars": len(content),
        "parsed": parsed,
        "profile": parsed
    }

@router.post("/parse-text")
def parse_raw_profile_text(req: TextIngestRequest):
    """
    Parses unstructured plain text or clipboard content into structured candidate profile.
    """
    if not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    parsed = parse_raw_resume_text(req.raw_text)
    if not parsed:
        raise HTTPException(status_code=400, detail="Could not extract candidate profile from provided text.")
    return {
        "status": "success",
        "extracted_chars": len(req.raw_text),
        "parsed": parsed
    }

@router.post("/commit")
def commit_profile_update(req: CommitProfileRequest):
    """
    Commits a parsed or edited profile into the active candidate profile with automated safe backup snapshot.
    """
    parsed = req.profile_data
    backup_file = backup_profile_to_file()
    
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
    UPDATE candidate_profiles SET
        is_onboarded = 1,
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
    cursor.execute("SELECT * FROM candidate_profiles WHERE is_active = 1 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return {
        "status": "success",
        "backup_created": backup_file,
        "profile": row_to_profile(row)
    }

@router.post("/reset", response_model=CandidateProfile)
def reset_active_profile():
    """
    Resets the candidate profile to a clean, unconfigured state.
    Creates an automatic backup snapshot first to protect historical data.
    """
    backup_file = backup_profile_to_file()
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    UPDATE candidate_profiles SET
        is_onboarded = 0,
        full_name = '',
        email = '',
        phone = '',
        location = '',
        citizenship = '',
        linkedin_url = '',
        github_url = '',
        portfolio_url = '',
        tagline = '',
        archetypes_json = '{}',
        experience_json = '[]',
        education_json = '[]',
        skills_json = '{}',
        preferences_json = '{"target_roles": ["Software Engineer", "Technical Program Manager"], "target_locations": ["Israel", "United States", "Remote"], "target_seniority": ["Mid-Level", "Senior"], "include_linkedin": true, "remote_only": false, "min_salary_usd": 0}',
        updated_at = ?
    WHERE is_active = 1
    """, (now_str,))
    conn.commit()
    cursor.execute("SELECT * FROM candidate_profiles WHERE is_active = 1 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row_to_profile(row)

@router.get("/backups")
def get_profile_backups():
    """Returns list of safe snapshot backups for candidate profiles."""
    return list_profile_backups()

@router.post("/restore/{backup_filename}")
def restore_profile(backup_filename: str):
    """Restores candidate profile from an automatic snapshot backup."""
    success = restore_profile_backup(backup_filename)
    if not success:
        raise HTTPException(status_code=404, detail="Backup file not found.")
    return {"status": "restored", "filename": backup_filename}

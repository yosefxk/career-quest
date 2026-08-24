import json
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.core.database import get_db
from app.models.job import JobCreate, JobUpdate, SnapshotCreate, RatingRequest
from app.engines.job_analyzer import analyze_job_fit

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

def row_to_job(row) -> dict:
    return {
        "id": row["id"],
        "candidate_id": row["candidate_id"],
        "company": row["company"],
        "title": row["title"],
        "url": row["url"],
        "location": row["location"],
        "salary": row["salary"],
        "status": row["status"],
        "match_score": row["match_score"],
        "job_description": row["job_description"],
        "analysis": json.loads(row["analysis_data"]) if row["analysis_data"] else {},
        "tailored_profile": row["tailored_profile"],
        "custom_summary": row["custom_summary"],
        "selected_bullets": json.loads(row["selected_bullets_json"]) if row["selected_bullets_json"] else [],
        "notes": row["notes"],
        "cv_pdf_filename": row["cv_pdf_filename"],
        "is_archived": row["is_archived"],
        "interest_rating": row["interest_rating"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"]
    }

@router.get("")
def get_jobs(show_archived: bool = False):
    conn = get_db()
    cursor = conn.cursor()
    if show_archived:
        cursor.execute("SELECT * FROM jobs ORDER BY updated_at DESC")
    else:
        cursor.execute("SELECT * FROM jobs WHERE is_archived = 0 ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [row_to_job(r) for r in rows]

@router.post("")
def create_job(job: JobCreate):
    conn = get_db()
    cursor = conn.cursor()
    
    # Check duplicates
    comp_norm = job.company.strip()
    title_norm = job.title.strip()
    cursor.execute("SELECT id, status FROM jobs WHERE LOWER(company) = LOWER(?) AND LOWER(title) = LOWER(?)", (comp_norm, title_norm))
    dup = cursor.fetchone()
    if dup:
        conn.close()
        raise HTTPException(
            status_code=409,
            detail={"message": "Job already exists in pipeline", "existing_id": dup["id"], "status": dup["status"]}
        )

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO jobs (
        candidate_id, company, title, url, location, salary, status, match_score,
        job_description, analysis_data, tailored_profile, custom_summary, selected_bullets_json,
        notes, is_archived, interest_rating, created_at, updated_at
    ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
    """, (
        comp_norm,
        title_norm,
        job.url,
        job.location,
        job.salary,
        job.status,
        job.match_score or 85,
        job.job_description,
        json.dumps(job.analysis_data) if job.analysis_data else None,
        job.tailored_profile or "technical_pm",
        job.custom_summary,
        json.dumps(job.selected_bullets) if job.selected_bullets else None,
        job.notes,
        now_str,
        now_str
    ))
    conn.commit()
    job_id = cursor.lastrowid
    conn.close()
    return {"id": job_id, "status": "created"}

@router.patch("/{job_id}")
def update_job(job_id: int, update: JobUpdate):
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    fields = []
    values = []
    for k, v in update.model_dump(exclude_unset=True).items():
        if k == "analysis_data":
            fields.append("analysis_data = ?")
            values.append(json.dumps(v) if v else None)
        elif k == "selected_bullets":
            fields.append("selected_bullets_json = ?")
            values.append(json.dumps(v) if v else None)
        else:
            fields.append(f"{k} = ?")
            values.append(v)
            
    if not fields:
        conn.close()
        return {"status": "no_change"}
        
    fields.append("updated_at = ?")
    values.append(now_str)
    values.append(job_id)
    
    cursor.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return {"status": "updated"}

@router.delete("/{job_id}")
def delete_job(job_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    cursor.execute("DELETE FROM application_snapshots WHERE job_id = ?", (job_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

@router.post("/{job_id}/retailor")
def retailor_job(job_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    job_row = cursor.fetchone()
    if not job_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")
        
    cursor.execute("SELECT * FROM candidate_profiles WHERE is_active = 1 LIMIT 1")
    cand_row = cursor.fetchone()
    candidate_profile = {
        "full_name": cand_row["full_name"],
        "tagline": cand_row["tagline"],
        "archetypes": json.loads(cand_row["archetypes_json"] or "{}"),
        "skills": json.loads(cand_row["skills_json"] or "{}")
    } if cand_row else {}
    
    analysis = analyze_job_fit(job_row["job_description"] or "", candidate_profile, job_row["url"] or "")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
    UPDATE jobs SET
        match_score = ?,
        analysis_data = ?,
        custom_summary = ?,
        tailored_profile = ?,
        updated_at = ?
    WHERE id = ?
    """, (
        analysis.get("match_score", 85),
        json.dumps(analysis),
        analysis.get("tailored_summary", ""),
        analysis.get("recommended_profile", "technical_pm"),
        now_str,
        job_id
    ))
    conn.commit()
    conn.close()
    return {"status": "retailored", "analysis": analysis}

@router.post("/{job_id}/snapshot")
def create_snapshot(job_id: int, req: SnapshotCreate):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    job_row = cursor.fetchone()
    if not job_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")
        
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO application_snapshots (
        job_id, candidate_id, company, title, stage, summary_text, selected_bullets,
        markdown_content, pdf_filename, job_description, created_at
    ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_id,
        job_row["company"],
        job_row["title"],
        req.stage or "applied",
        req.custom_summary or job_row["custom_summary"],
        json.dumps(req.selected_bullets) if req.selected_bullets else job_row["selected_bullets_json"],
        "",
        job_row["cv_pdf_filename"],
        req.job_description or job_row["job_description"],
        now_str
    ))
    
    # Update stage to applied
    cursor.execute("UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?", (req.stage or "applied", now_str, job_id))
    conn.commit()
    conn.close()
    return {"status": "snapshot_frozen", "stage": req.stage or "applied"}

@router.get("/{job_id}/snapshots")
def get_job_snapshots(job_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM application_snapshots WHERE job_id = ? ORDER BY created_at DESC", (job_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/{job_id}/interest")
def rate_job_interest(job_id: int, req: RatingRequest):
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE jobs SET interest_rating = ?, updated_at = ? WHERE id = ?", (req.rating, now_str, job_id))
    conn.commit()
    conn.close()
    return {"status": "success", "rating": req.rating}

@router.post("/{job_id}/archive")
def archive_job(job_id: int):
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE jobs SET is_archived = 1, updated_at = ? WHERE id = ?", (now_str, job_id))
    conn.commit()
    conn.close()
    return {"status": "archived"}

@router.post("/{job_id}/unarchive")
def unarchive_job(job_id: int):
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE jobs SET is_archived = 0, updated_at = ? WHERE id = ?", (now_str, job_id))
    conn.commit()
    conn.close()
    return {"status": "restored"}

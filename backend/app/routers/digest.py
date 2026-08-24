import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.core.database import get_db
from app.models.job import RatingRequest
from app.models.digest import CompanyCreate
from app.engines.scraper_engine import stream_opportunity_scan

router = APIRouter(prefix="/api/v1/digest", tags=["digest"])

@router.get("")
def get_digest(
    q: Optional[str] = None,
    region: Optional[str] = "all",
    category: Optional[str] = "all",
    role_family: Optional[str] = "all",
    yoe: Optional[str] = "all",
    min_match: Optional[int] = 0,
    sort_by: Optional[str] = "match_desc",
    show_archived: Optional[bool] = False,
    interest: Optional[str] = "all"
):
    conn = get_db()
    cursor = conn.cursor()
    
    query_parts = []
    params = []
    
    if not show_archived:
        query_parts.append("is_archived = 0")
    else:
        query_parts.append("is_archived = 1")
        
    if interest == "liked":
        query_parts.append("interest_rating = 1")
    elif interest == "disliked":
        query_parts.append("interest_rating = -1")
    elif interest == "unrated":
        query_parts.append("interest_rating = 0")
        
    if region and region != "all":
        query_parts.append("region = ?")
        params.append(region)
        
    if category and category != "all":
        query_parts.append("category = ?")
        params.append(category)
        
    if role_family and role_family != "all":
        query_parts.append("role_family = ?")
        params.append(role_family)
        
    if min_match and min_match > 0:
        query_parts.append("match_score >= ?")
        params.append(min_match)
        
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        query_parts.append("(LOWER(company) LIKE ? OR LOWER(title) LIKE ? OR LOWER(location) LIKE ?)")
        params.extend([term, term, term])
        
    where_clause = f"WHERE {' AND '.join(query_parts)}" if query_parts else ""
    
    order_clause = "ORDER BY match_score DESC, posted_date DESC"
    if sort_by == "match_asc": order_clause = "ORDER BY match_score ASC"
    elif sort_by == "date_desc": order_clause = "ORDER BY posted_date DESC"
    elif sort_by == "salary_desc": order_clause = "ORDER BY salary_max DESC"
    
    cursor.execute(f"SELECT * FROM discovery_digest {where_clause} {order_clause}", params)
    rows = cursor.fetchall()
    conn.close()
    
    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "job_key": r["job_key"],
            "company": r["company"],
            "title": r["title"],
            "location": r["location"],
            "region": r["region"],
            "category": r["category"],
            "url": r["url"],
            "source": r["source"],
            "salary_min": r["salary_min"],
            "salary_max": r["salary_max"],
            "salary_display": r["salary_display"],
            "match_score": r["match_score"],
            "match_highlights": json.loads(r["match_highlights"]) if r["match_highlights"] else [],
            "role_family": r["role_family"],
            "yoe_min": r["yoe_min"],
            "yoe_max": r["yoe_max"],
            "yoe_display": r["yoe_display"],
            "snippet": r["snippet"],
            "posted_date": r["posted_date"],
            "in_pipeline": r["in_pipeline"],
            "is_archived": r["is_archived"],
            "interest_rating": r["interest_rating"],
            "created_at": r["created_at"]
        })
    return items

@router.get("/scan/stream")
def scan_digest_stream(
    location: Optional[str] = None,
    role: Optional[str] = None,
    include_linkedin: bool = True
):
    target_locations = [location] if location and location != "all" else None
    target_roles = [role] if role and role != "all" else None
    def event_stream():
        for event in stream_opportunity_scan(target_roles=target_roles, target_locations=target_locations, include_linkedin=include_linkedin):
            yield f"data: {json.dumps(event)}\n\n"
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.post("/{digest_id}/add-to-pipeline")
def add_digest_to_pipeline(digest_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM discovery_digest WHERE id = ?", (digest_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Digest item not found")
        
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO jobs (
        candidate_id, company, title, url, location, salary, status, match_score,
        job_description, tailored_profile, is_archived, interest_rating, created_at, updated_at
    ) VALUES (1, ?, ?, ?, ?, ?, 'wishlist', ?, ?, 'technical_pm', 0, ?, ?, ?)
    """, (
        row["company"],
        row["title"],
        row["url"],
        row["location"],
        row["salary_display"],
        row["match_score"],
        row["snippet"],
        row["interest_rating"],
        now_str,
        now_str
    ))
    job_id = cursor.lastrowid
    cursor.execute("UPDATE discovery_digest SET in_pipeline = 1 WHERE id = ?", (digest_id,))
    conn.commit()
    conn.close()
    return {"status": "added", "job_id": job_id}

@router.post("/{digest_id}/interest")
def rate_digest_interest(digest_id: int, req: RatingRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE discovery_digest SET interest_rating = ? WHERE id = ?", (req.rating, digest_id))
    conn.commit()
    conn.close()
    return {"status": "success", "rating": req.rating}

@router.post("/{digest_id}/archive")
def archive_digest_item(digest_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE discovery_digest SET is_archived = 1 WHERE id = ?", (digest_id,))
    conn.commit()
    conn.close()
    return {"status": "archived"}

@router.post("/{digest_id}/unarchive")
def unarchive_digest_item(digest_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE discovery_digest SET is_archived = 0 WHERE id = ?", (digest_id,))
    conn.commit()
    conn.close()
    return {"status": "unarchived"}

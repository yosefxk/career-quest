import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from app.core.database import get_db
from app.engines.copilot_engine import (
    process_copilot_turn,
    get_all_directives,
    get_active_directives
)

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])

class ChatRequest(BaseModel):
    message: str
    focused_job_id: Optional[int] = None

class DirectiveCreateRequest(BaseModel):
    rule_text: str
    category: Optional[str] = "cv_style"

class DirectiveUpdateRequest(BaseModel):
    rule_text: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/messages")
def get_chat_messages(limit: int = 50):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, session_id, role, content, metadata_json, created_at 
    FROM copilot_messages 
    ORDER BY id ASC 
    LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    messages = []
    for r in rows:
        meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
        messages.append({
            "id": r["id"],
            "role": r["role"],
            "content": r["content"],
            "metadata": meta,
            "created_at": r["created_at"]
        })
    return messages

@router.post("/chat")
def send_chat_message(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    result = process_copilot_turn(user_message=req.message, focused_job_id=req.focused_job_id)
    return result

@router.delete("/messages")
def clear_chat_history():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM copilot_messages")
    conn.commit()
    conn.close()
    return {"status": "cleared"}

@router.get("/directives")
def list_directives():
    conn = get_db()
    directives = get_all_directives(conn)
    conn.close()
    return directives

@router.post("/directives")
def create_directive(req: DirectiveCreateRequest):
    if not req.rule_text.strip():
        raise HTTPException(status_code=400, detail="Rule text cannot be empty")
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO user_directives (candidate_id, category, rule_text, is_active, source, created_at, updated_at)
    VALUES (1, ?, ?, 1, 'manual', ?, ?)
    """, (req.category or "cv_style", req.rule_text.strip(), now_str, now_str))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": new_id,
        "category": req.category or "cv_style",
        "rule_text": req.rule_text.strip(),
        "is_active": True,
        "source": "manual",
        "created_at": now_str
    }

@router.patch("/directives/{directive_id}")
def update_directive(directive_id: int, req: DirectiveUpdateRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_directives WHERE id = ?", (directive_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Directive not found")
        
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    fields = []
    values = []
    
    if req.rule_text is not None:
        fields.append("rule_text = ?")
        values.append(req.rule_text.strip())
    if req.category is not None:
        fields.append("category = ?")
        values.append(req.category)
    if req.is_active is not None:
        fields.append("is_active = ?")
        values.append(1 if req.is_active else 0)
        
    if fields:
        fields.append("updated_at = ?")
        values.append(now_str)
        values.append(directive_id)
        cursor.execute(f"UPDATE user_directives SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        
    cursor.execute("SELECT * FROM user_directives WHERE id = ?", (directive_id,))
    row = cursor.fetchone()
    conn.close()
    return {
        "id": row["id"],
        "category": row["category"],
        "rule_text": row["rule_text"],
        "is_active": bool(row["is_active"]),
        "source": row["source"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"]
    }

@router.delete("/directives/{directive_id}")
def delete_directive(directive_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_directives WHERE id = ?", (directive_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": directive_id}

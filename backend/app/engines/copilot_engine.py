import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from app.core.config import settings
from app.core.database import get_db
from app.core.llm_gateway import llm
from app.engines.job_analyzer import (
    extract_job_text_from_url,
    analyze_job_fit,
    generate_recruiter_inmails,
    generate_company_intel,
    generate_role_mock_interview,
    clean_input_url
)
from app.engines.cv_renderer import render_cv_html, generate_cv_markdown, generate_cv_pdf

def get_active_directives(conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    close_after = False
    if conn is None:
        conn = get_db()
        close_after = True
    cursor = conn.cursor()
    cursor.execute("SELECT id, category, rule_text, is_active, source, created_at FROM user_directives WHERE is_active = 1 ORDER BY id ASC")
    rows = cursor.fetchall()
    if close_after:
        conn.close()
    return [{"id": r["id"], "category": r["category"], "rule_text": r["rule_text"], "source": r["source"]} for r in rows]

def get_all_directives(conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    close_after = False
    if conn is None:
        conn = get_db()
        close_after = True
    cursor = conn.cursor()
    cursor.execute("SELECT id, category, rule_text, is_active, source, created_at FROM user_directives ORDER BY id ASC")
    rows = cursor.fetchall()
    if close_after:
        conn.close()
    return [{
        "id": r["id"],
        "category": r["category"],
        "rule_text": r["rule_text"],
        "is_active": bool(r["is_active"]),
        "source": r["source"],
        "created_at": r["created_at"]
    } for r in rows]

def get_candidate_profile_dict(conn: sqlite3.Connection) -> Dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM candidate_profiles WHERE is_active = 1 LIMIT 1")
    row = cursor.fetchone()
    if not row:
        return {
            "id": 1,
            "full_name": "Candidate",
            "email": "candidate@example.com",
            "phone": "",
            "location": "Global / Remote",
            "citizenship": "",
            "linkedin_url": "",
            "github_url": "",
            "portfolio_url": "",
            "tagline": "",
            "archetypes": {},
            "skills": {},
            "experience": [],
            "education": []
        }
    return {
        "id": row["id"],
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

def extract_directive_from_turn(user_text: str) -> Optional[Dict[str, str]]:
    direct_match = re.search(r'(?:remember this rule|remember rule|teach rule|rule|remember)\s*:\s*(.+)$', user_text, re.IGNORECASE)
    if direct_match:
        rule_extracted = direct_match.group(1).strip()
        if len(rule_extracted) > 5:
            cat = "cv_style"
            low = rule_extracted.lower()
            if any(w in low for w in ["tone", "phrase", "word", "passive", "avoid", "spearhead", "jargon"]):
                cat = "tone"
            elif any(w in low for w in ["page", "budget", "bullet count", "length", "margin", "font"]):
                cat = "formatting"
            elif any(w in low for w in ["salary", "remote", "location", "country", "target"]):
                cat = "job_preference"
            return {
                "category": cat,
                "rule_text": rule_extracted
            }

    heuristic_triggers = ["remember", "rule", "always", "never", "i prefer", "prefer", "don't use", "do not use", "make sure to", "ensure that", "my style", "avoid"]
    lower = user_text.lower()
    if not any(k in lower for k in heuristic_triggers):
        return None

    prompt = f'''Analyze this user message to determine if they are teaching a persistent preference, style rule, constraint, or opinion for their career materials (CV, summaries, bullets, job preferences, tone).

User Message:
"""
{user_text}
"""

Output strictly JSON:
{{
  "is_directive": true,
  "category": "cv_style" or "tone" or "formatting" or "job_preference" or "general",
  "rule_text": "A clear, concise, self-contained rule statement capturing the user's preference."
}}
If the message is just a general question or doesn't establish a persistent rule, set "is_directive": false.
'''
    res = llm.generate_json(prompt, system_prompt="Output valid JSON only.")
    if res and res.get("is_directive") and res.get("rule_text"):
        return {
            "category": res.get("category", "cv_style"),
            "rule_text": res.get("rule_text").strip()
        }
    return None

def find_job_by_identifier(conn: sqlite3.Connection, identifier: str, focused_job_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    cur = conn.cursor()
    id_clean = re.sub(r'[^0-9]', '', identifier)
    if id_clean:
        try:
            jid = int(id_clean)
            cur.execute("SELECT * FROM jobs WHERE id = ?", (jid,))
            row = cur.fetchone()
            if row:
                return dict(row)
        except Exception:
            pass
            
    comp_clean = identifier.strip().lower()
    if len(comp_clean) >= 2 and comp_clean not in ["this", "the", "job", "role", "position"]:
        cur.execute("SELECT * FROM jobs WHERE LOWER(company) LIKE ? ORDER BY id DESC LIMIT 1", (f"%{comp_clean}%",))
        row = cur.fetchone()
        if row:
            return dict(row)
            
    if focused_job_id:
        cur.execute("SELECT * FROM jobs WHERE id = ?", (focused_job_id,))
        row = cur.fetchone()
        if row:
            return dict(row)
            
    return None

def execute_ingest_action(conn: sqlite3.Connection, url: str, user_message: str) -> Optional[Dict[str, Any]]:
    clean_url = clean_input_url(url)
    if not clean_url:
        return None
        
    cur = conn.cursor()
    cur.execute("SELECT id, company, title, status, match_score FROM jobs WHERE url = ?", (clean_url,))
    existing = cur.fetchone()
    if existing:
        return {
            "type": "job_already_exists",
            "job_id": existing["id"],
            "company": existing["company"],
            "title": existing["title"],
            "status": existing["status"],
            "match_score": existing["match_score"],
            "details": f"Job **{existing['company']} - {existing['title']}** is already in your pipeline (Stage: **{existing['status'].upper()}**, Match: **{existing['match_score']}%**, ID #{existing['id']}).",
            "toast": f"{existing['company']} is already in pipeline ({existing['status'].upper()})"
        }
        
    job_text, pref_title, _ = extract_job_text_from_url(clean_url)
    if not job_text:
        job_text = f"Job listing imported via Career Coach from {clean_url}"
        
    cand_profile = get_candidate_profile_dict(conn)
    analysis = analyze_job_fit(job_text, cand_profile, pref_title=pref_title)
    
    company = analysis.get("company") or "Target Company"
    title = analysis.get("title") or pref_title or "Position"
    match_score = analysis.get("match_score", 85)
    custom_summary = analysis.get("tailored_summary", "")
    
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO jobs (candidate_id, company, title, url, status, match_score, job_description, analysis_data, custom_summary, created_at, updated_at)
        VALUES (1, ?, ?, ?, 'wishlist', ?, ?, ?, ?, ?, ?)
    """, (
        company, title, clean_url, match_score, job_text,
        json.dumps(analysis), custom_summary, now, now
    ))
    conn.commit()
    new_id = cur.lastrowid
    
    return {
        "type": "job_ingested",
        "job_id": new_id,
        "company": company,
        "title": title,
        "match_score": match_score,
        "status": "wishlist",
        "details": f"Successfully ingested and parsed **{company} - {title}** into Application Studio (Job #{new_id}, Match: **{match_score}%**, Stage: **WISHLIST**).",
        "toast": f"Ingested {company} - {title} ({match_score}% Match)"
    }

def execute_ingest_text_action(conn: sqlite3.Connection, raw_text: str) -> Optional[Dict[str, Any]]:
    if len(raw_text.strip()) < 15:
        return None
        
    cand_profile = get_candidate_profile_dict(conn)
    pref_company = ""
    pref_title = ""
    m_split = re.match(r'^([A-Za-z0-9\s]+?)\s*[-–—]\s*([A-Za-z0-9\s/]+?):\s*(.+)$', raw_text, re.DOTALL)
    if m_split:
        pref_company = m_split.group(1).strip()
        pref_title = m_split.group(2).strip()
        raw_text = m_split.group(3).strip()
        
    analysis = analyze_job_fit(raw_text, cand_profile, pref_company=pref_company, pref_title=pref_title)
    company = analysis.get("company") or pref_company or "Target Company"
    title = analysis.get("title") or pref_title or "Position"
    match_score = analysis.get("match_score", 85)
    custom_summary = analysis.get("tailored_summary", "")
    
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO jobs (candidate_id, company, title, url, status, match_score, job_description, analysis_data, custom_summary, created_at, updated_at)
        VALUES (1, ?, ?, '', 'wishlist', ?, ?, ?, ?, ?, ?)
    """, (
        company, title, match_score, raw_text,
        json.dumps(analysis), custom_summary, now, now
    ))
    conn.commit()
    new_id = cur.lastrowid
    
    return {
        "type": "job_ingested",
        "job_id": new_id,
        "company": company,
        "title": title,
        "match_score": match_score,
        "status": "wishlist",
        "details": f"Ingested **{company} - {title}** from text snippet into Application Studio (Job #{new_id}, Match: **{match_score}%**, Stage: **WISHLIST**).",
        "toast": f"Ingested {company} - {title} ({match_score}% Match)"
    }

def execute_update_action(conn: sqlite3.Connection, identifier: str, new_status: Optional[str] = None, notes: Optional[str] = None, rating: Optional[int] = None, archive: Optional[bool] = None, focused_job_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    job = find_job_by_identifier(conn, identifier, focused_job_id)
    if not job:
        return None
        
    cur = conn.cursor()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    updates = ["updated_at = ?"]
    params = [now]
    action_details = []
    
    if new_status:
        valid_status = new_status.lower()
        if valid_status in ["wishlist", "tailoring", "applied", "screen", "technical", "onsite", "interviewing", "offer", "rejected"]:
            if valid_status == "interviewing":
                valid_status = "screen"
            updates.append("status = ?")
            params.append(valid_status)
            action_details.append(f"stage &rarr; **{valid_status.upper()}**")
            
    if notes:
        existing_notes = job.get("notes") or ""
        combined_notes = (existing_notes + "\n" + f"[{now[:10]}] {notes}").strip() if existing_notes else f"[{now[:10]}] {notes}"
        updates.append("notes = ?")
        params.append(combined_notes)
        action_details.append(f"added note: *'{notes}'*")
        
    if rating is not None:
        updates.append("interest_rating = ?")
        params.append(rating)
        action_details.append(f"interest rating &rarr; **{rating}★**")
        
    if archive is not None:
        updates.append("is_archived = ?")
        params.append(1 if archive else 0)
        action_details.append("archived" if archive else "unarchived")
        
    if len(updates) > 1:
        params.append(job["id"])
        cur.execute(f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        
        detail_str = ", ".join(action_details)
        return {
            "type": "job_updated",
            "job_id": job["id"],
            "company": job["company"],
            "title": job["title"],
            "details": f"Updated **{job['company']} - {job['title']}** (#{job['id']}): {detail_str}.",
            "toast": f"Updated {job['company']} (#{job['id']})"
        }
    return None

def execute_tailor_action(conn: sqlite3.Connection, identifier: str, focused_job_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    job = find_job_by_identifier(conn, identifier, focused_job_id)
    if not job:
        return None
        
    cand_profile = get_candidate_profile_dict(conn)
    job_desc = job.get("job_description") or f"{job.get('company')} {job.get('title')}"
    
    analysis = {}
    if job.get("analysis_data"):
        try:
            analysis = json.loads(job["analysis_data"])
        except Exception:
            pass
    if not analysis or "match_score" not in analysis:
        analysis = analyze_job_fit(job_desc, cand_profile, pref_company=job.get("company"), pref_title=job.get("title"))
        
    score = analysis.get("match_score", job.get("match_score", 85))
    custom_summary = analysis.get("tailored_summary") or job.get("custom_summary") or cand_profile.get("tagline", "")
    
    selected_bullets = None
    if job.get("selected_bullets_json"):
        try:
            selected_bullets = json.loads(job["selected_bullets_json"])
        except Exception:
            pass

    html = render_cv_html(profile_data=cand_profile, custom_summary=custom_summary, selected_bullet_ids=selected_bullets)
    md = generate_cv_markdown(profile_data=cand_profile, custom_summary=custom_summary, selected_bullet_ids=selected_bullets)
    
    cand_name = cand_profile.get("full_name", "Resume")
    date_str = datetime.now().strftime("%Y-%m-%d")
    company_clean = re.sub(r'[^a-zA-Z0-9]+', '_', job.get("company", "Company")).strip('_')
    role_clean = re.sub(r'[^a-zA-Z0-9]+', '_', job.get("title", "Role")).strip('_')
    folder_name = f"{date_str}_{company_clean}_{role_clean}"
    
    rel_path = generate_cv_pdf(html, folder_name=folder_name, candidate_name=cand_name, markdown_content=md)
    
    cur = conn.cursor()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        UPDATE jobs 
        SET cv_pdf_filename = ?, custom_summary = ?, match_score = ?, updated_at = ?
        WHERE id = ?
    """, (rel_path, custom_summary, score, now, job["id"]))
    conn.commit()
    
    return {
        "type": "cv_tailored",
        "job_id": job["id"],
        "company": job["company"],
        "title": job["title"],
        "match_score": score,
        "pdf_filename": rel_path,
        "custom_summary": custom_summary,
        "details": f"Tailored 1-page CV generated for **{job['company']} - {job['title']}** (Score: **{score}%**).\n- PDF file: {rel_path}\n- Custom Summary: *\"{custom_summary}\"*",
        "toast": f"Tailored 1-page CV generated for {job['company']}!"
    }

def execute_intel_action(conn: sqlite3.Connection, identifier: str, intel_type: str, focused_job_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    job = find_job_by_identifier(conn, identifier, focused_job_id)
    if not job:
        return None
        
    company = job.get("company", "")
    title = job.get("title", "")
    desc = job.get("job_description", "")
    cand_profile = get_candidate_profile_dict(conn)
    directives = get_active_directives(conn)
    
    if intel_type == "mock_interview":
        data = generate_role_mock_interview(company, title, desc, cand_profile, directives=directives)
        return {
            "type": "mock_interview_generated",
            "job_id": job["id"],
            "company": company,
            "title": title,
            "data": data,
            "details": f"Generated 10 role-specific mock interview questions and STAR answer blueprints for **{company} - {title}**.",
            "toast": f"Generated Mock Interview questions for {company}!"
        }
    elif intel_type == "inmail":
        data = generate_recruiter_inmails(company, title, desc, cand_profile, directives=directives)
        return {
            "type": "inmail_generated",
            "job_id": job["id"],
            "company": company,
            "title": title,
            "data": data,
            "details": f"Synthesized 3 tailored LinkedIn InMail outreach variants (Hiring Manager, Recruiter, Peer) for **{company} - {title}**.",
            "toast": f"Generated LinkedIn InMails for {company}!"
        }
    elif intel_type == "company_intel":
        data = generate_company_intel(company, title, desc)
        return {
            "type": "company_intel_generated",
            "job_id": job["id"],
            "company": company,
            "title": title,
            "data": data,
            "details": f"Compiled Executive Company Intelligence Dossier for **{company}** ({title}).",
            "toast": f"Generated Company Intel Brief for {company}!"
        }
    return None

def detect_and_execute_action(conn: sqlite3.Connection, user_message: str, focused_job_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    msg_clean = user_message.strip()
    msg_lower = msg_clean.lower()
    
    url_match = re.search(r'https?://[^\s<>"]+', msg_clean)
    if url_match:
        url = url_match.group(0)
        return execute_ingest_action(conn, url, msg_clean)
        
    if any(msg_lower.startswith(k) for k in ["ingest job", "add job", "track job", "create job"]):
        colon_split = msg_clean.split(":", 1)
        if len(colon_split) > 1:
            raw_text = colon_split[1].strip()
            return execute_ingest_text_action(conn, raw_text)

    status_match = re.search(r'(?:mark|set|move|change|update)\s+(?:(?:the\s+)?job\s+(?:#|id\s*)?(\d+)|([A-Za-z0-9\s\-]+?))\s+(?:as|to|status\s+to)?\s*(applied|interviewing|screen|technical|onsite|offer|rejected|wishlist)', msg_clean, re.IGNORECASE)
    if status_match:
        target_id_str = status_match.group(1) or status_match.group(2) or ""
        new_status = status_match.group(3)
        return execute_update_action(conn, target_id_str, new_status=new_status, focused_job_id=focused_job_id)
        
    simple_status_match = re.search(r'^(?:mark\s+as|set\s+status\s+to|change\s+to|move\s+to)\s+(applied|interviewing|screen|technical|onsite|offer|rejected|wishlist)$', msg_clean, re.IGNORECASE)
    if simple_status_match and focused_job_id:
        return execute_update_action(conn, "", new_status=simple_status_match.group(1), focused_job_id=focused_job_id)

    note_match = re.search(r'(?:add\s+note|note)\s+(?:to\s+(?:(?:the\s+)?job\s+(?:#|id\s*)?(\d+)|([A-Za-z0-9\s\-]+?))(?:\s*:\s*|\s+))(.+)', msg_clean, re.IGNORECASE)
    if note_match:
        target_id_str = note_match.group(1) or note_match.group(2) or ""
        note_content = note_match.group(3).strip()
        return execute_update_action(conn, target_id_str, notes=note_content, focused_job_id=focused_job_id)
    elif focused_job_id and re.search(r'^(?:add\s+note|note)\s*:\s*(.+)$', msg_clean, re.IGNORECASE):
        m = re.search(r'^(?:add\s+note|note)\s*:\s*(.+)$', msg_clean, re.IGNORECASE)
        return execute_update_action(conn, "", notes=m.group(1).strip(), focused_job_id=focused_job_id)

    archive_match = re.search(r'(?:archive)\s+(?:(?:the\s+)?job\s+(?:#|id\s*)?(\d+)|([A-Za-z0-9\s\-]+))', msg_clean, re.IGNORECASE)
    if archive_match:
        target_id_str = archive_match.group(1) or archive_match.group(2) or ""
        return execute_update_action(conn, target_id_str, archive=True, focused_job_id=focused_job_id)

    if any(k in msg_lower for k in ["tailor cv", "tailor resume", "generate cv", "generate resume", "build cv", "build resume", "create resume"]):
        target_id_str = ""
        id_m = re.search(r'(?:for\s+(?:(?:the\s+)?job\s+(?:#|id\s*)?(\d+)|([A-Za-z0-9\s\-]+)))', msg_clean, re.IGNORECASE)
        if id_m:
            target_id_str = id_m.group(1) or id_m.group(2) or ""
        return execute_tailor_action(conn, target_id_str, focused_job_id=focused_job_id)

    if any(k in msg_lower for k in ["mock interview", "interview questions", "practice questions"]):
        target_id_str = ""
        id_m = re.search(r'(?:for\s+(?:(?:the\s+)?job\s+(?:#|id\s*)?(\d+)|([A-Za-z0-9\s\-]+)))', msg_clean, re.IGNORECASE)
        if id_m:
            target_id_str = id_m.group(1) or id_m.group(2) or ""
        return execute_intel_action(conn, target_id_str, "mock_interview", focused_job_id=focused_job_id)

    if any(k in msg_lower for k in ["inmail", "outreach", "cold message", "reach out to recruiter", "reach out to hiring manager"]):
        target_id_str = ""
        id_m = re.search(r'(?:for\s+(?:(?:the\s+)?job\s+(?:#|id\s*)?(\d+)|([A-Za-z0-9\s\-]+)))', msg_clean, re.IGNORECASE)
        if id_m:
            target_id_str = id_m.group(1) or id_m.group(2) or ""
        return execute_intel_action(conn, target_id_str, "inmail", focused_job_id=focused_job_id)

    if any(k in msg_lower for k in ["company intel", "intelligence brief", "research company"]):
        target_id_str = ""
        id_m = re.search(r'(?:for\s+(?:(?:the\s+)?job\s+(?:#|id\s*)?(\d+)|([A-Za-z0-9\s\-]+)))', msg_clean, re.IGNORECASE)
        if id_m:
            target_id_str = id_m.group(1) or id_m.group(2) or ""
        return execute_intel_action(conn, target_id_str, "company_intel", focused_job_id=focused_job_id)

    action_keywords = ["ingest", "update", "mark", "status", "applied", "interviewing", "tailor", "build resume", "generate cv"]
    if any(w in msg_lower for w in action_keywords):
        try:
            intent_prompt = f"""Analyze if the user wants to perform an action on their job pipeline in Career Vault / Career Quest.
Message: "{msg_clean}"
Focused Job ID: {focused_job_id}

Output valid JSON ONLY:
{{
  "action": "ingest_job" | "update_job" | "tailor_cv" | "mock_interview" | "inmail" | "company_intel" | "none",
  "target_job_identifier": "job ID or company name, or empty string",
  "status": "applied" | "interviewing" | "screen" | "technical" | "onsite" | "offer" | "rejected" | "wishlist" | null,
  "notes": "note text if user provided one" | null,
  "url": "url if provided" | null
}}"""
            parsed = llm.generate_json(intent_prompt, timeout=8.0)
            if parsed and parsed.get("action") and parsed.get("action") != "none":
                act = parsed.get("action")
                tgt = parsed.get("target_job_identifier") or ""
                if act == "ingest_job" and parsed.get("url"):
                    return execute_ingest_action(conn, parsed["url"], msg_clean)
                elif act == "update_job":
                    return execute_update_action(conn, tgt, new_status=parsed.get("status"), notes=parsed.get("notes"), focused_job_id=focused_job_id)
                elif act == "tailor_cv":
                    return execute_tailor_action(conn, tgt, focused_job_id=focused_job_id)
                elif act in ["mock_interview", "inmail", "company_intel"]:
                    return execute_intel_action(conn, tgt, act, focused_job_id=focused_job_id)
        except Exception:
            pass

    return None

def build_copilot_system_prompt(candidate_profile: Dict[str, Any], directives: List[Dict[str, Any]], active_jobs: List[Dict[str, Any]], focused_job: Optional[Dict[str, Any]] = None) -> str:
    cand_name = candidate_profile.get("full_name", "Candidate")
    tagline = candidate_profile.get("tagline", "Technology Professional")
    skills = json.dumps(candidate_profile.get("skills", {}))
    
    experience_bullets = []
    for exp in candidate_profile.get("experience", []):
        comp = exp.get("company", "Company")
        role = exp.get("role", "Role")
        bullets = [b.get("text", "") for b in exp.get("bullets", [])]
        experience_bullets.append(f"• {comp} ({role}): " + " | ".join(bullets[:3]))
    exp_summary = "\n".join(experience_bullets[:6])

    directives_list = "\n".join([f"- [{d['category'].upper()}] {d['rule_text']}" for d in directives]) if directives else "None yet."
    
    pipeline_summary = f"{len(active_jobs)} total tracked jobs across Wishlist, Tailoring, Applied, Screen, and Technical stages."

    focused_job_block = ""
    if focused_job:
        focused_job_block = f"""
CURRENT FOCUSED JOB IN CONTEXT:
Job ID: #{focused_job.get('id')}
Company: {focused_job.get('company')}
Title: {focused_job.get('title')}
Location: {focused_job.get('location')}
Salary: {focused_job.get('salary', 'Competitive')}
Status: {focused_job.get('status')}
Match Score: {focused_job.get('match_score')}%
Tailored Summary: {focused_job.get('custom_summary', 'None')}
Job Description Snippet: {str(focused_job.get('job_description') or '')[:1200]}
"""

    return f"""You are CareerQuest Career Coach, an elite executive career strategist, ATS resume specialist, and technical interview advisor.
You are collaborating directly with candidate {cand_name} ({tagline}).

CANDIDATE BACKGROUND & SKILLS:
{skills}

KEY EXPERIENCE BULLETS:
{exp_summary}

JOB PIPELINE CONTEXT:
{pipeline_summary}
{focused_job_block}

USER'S TAUGHT PREFERENCES & STYLE DIRECTIVES (STRICTLY ENFORCE THESE RULES):
{directives_list}

YOUR MISSION & OPERATIONAL POWERS:
1. Provide sharp, metric-driven, actionable advice on CV bullets, executive summaries, ATS keyword targeting, and interview prep.
2. STRICTLY honor the candidate's Learned Directives shown above. When giving advice or rewriting bullets, apply their exact tone, formatting, and style preferences.
3. You have DIRECT OPERATIONAL ACCESS inside CareerQuest:
   - Ingesting Jobs: When the user shares a job URL or job description, you directly ingest, analyze, and save it to their Application Studio.
   - Managing Pipeline: When asked to update, mark, or archive a job (e.g. "Mark Waymo as applied", "Set status to interviewing", "Add note..."), you update the database in real time.
   - Tailoring CVs: When asked to tailor a CV (e.g. "Tailor CV for this job"), you synthesize custom executive summaries, select optimal 1-page bullets, and compile the tailored PDF.
   - Interview & Outreach Intelligence: You synthesize role-specific STAR mock interviews, recruiter InMail variants, and company dossiers.
4. When an operational action was executed, acknowledge the changes made clearly and provide strategic next steps.
5. When the user provides feedback, opinions, or stylistic constraints on their CVs or job search, acknowledge their direction and confirm that it is being applied to their style memory.
6. Format output in crisp GitHub-flavored Markdown with clear headings, bullet points, and concise language. Avoid corporate fluff.
"""

def process_copilot_turn(user_message: str, focused_job_id: Optional[int] = None) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    
    cand_profile = get_candidate_profile_dict(conn)
    
    executed_action = detect_and_execute_action(conn, user_message, focused_job_id=focused_job_id)
    if executed_action and executed_action.get("job_id"):
        focused_job_id = executed_action.get("job_id")

    directives = get_active_directives(conn)
    
    cursor.execute("SELECT id, company, title, status, location, salary, match_score, custom_summary, job_description FROM jobs WHERE is_archived = 0")
    job_rows = cursor.fetchall()
    active_jobs = [dict(r) for r in job_rows]
    
    focused_job = None
    if focused_job_id:
        for j in active_jobs:
            if j["id"] == focused_job_id:
                focused_job = j
                break
                
    cursor.execute("SELECT role, content FROM copilot_messages ORDER BY id DESC LIMIT 10")
    history_rows = cursor.fetchall()
    messages = [{"role": r["role"], "content": r["content"]} for r in reversed(history_rows)]
    messages.append({"role": "user", "content": user_message})
    
    system_prompt = build_copilot_system_prompt(cand_profile, directives, active_jobs, focused_job)
    if executed_action:
        system_prompt += f"""

OPERATIONAL ACTION EXECUTED IN THIS TURN:
Action Type: {executed_action.get('type')}
Details: {executed_action.get('details')}
{('Generated Data: ' + json.dumps(executed_action.get('data'))) if executed_action.get('data') else ''}

INSTRUCTION: Warmly confirm the operational execution to the candidate. Present key metrics/summaries cleanly in markdown. Provide high-level strategic next steps for this role/application.
"""

    assistant_reply = llm.chat(messages, system_prompt=system_prompt)
    if not assistant_reply:
        assistant_reply = "I've reviewed your request. You can configure active style directives in the side panel to guide how I tailor all future CVs and applications."
        
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    new_directive = extract_directive_from_turn(user_message)
    saved_directive = None
    if new_directive:
        cursor.execute("""
        INSERT INTO user_directives (candidate_id, category, rule_text, is_active, source, created_at, updated_at)
        VALUES (1, ?, ?, 1, 'chat', ?, ?)
        """, (new_directive["category"], new_directive["rule_text"], now_str, now_str))
        directive_id = cursor.lastrowid
        saved_directive = {
            "id": directive_id,
            "category": new_directive["category"],
            "rule_text": new_directive["rule_text"],
            "source": "chat",
            "is_active": True
        }
        
    cursor.execute("""
    INSERT INTO copilot_messages (session_id, candidate_id, role, content, metadata_json, created_at)
    VALUES ('default', 1, 'user', ?, ?, ?)
    """, (user_message, json.dumps({"focused_job_id": focused_job_id}), now_str))
    
    assistant_meta = {
        "saved_directive": saved_directive,
        "action_executed": executed_action,
        "focused_job_id": focused_job_id
    }
    cursor.execute("""
    INSERT INTO copilot_messages (session_id, candidate_id, role, content, metadata_json, created_at)
    VALUES ('default', 1, 'assistant', ?, ?, ?)
    """, (assistant_reply, json.dumps(assistant_meta), now_str))
    
    conn.commit()
    conn.close()
    
    return {
        "reply": assistant_reply,
        "new_directive": saved_directive,
        "action_executed": executed_action,
        "focused_job_id": focused_job_id,
        "created_at": now_str
    }

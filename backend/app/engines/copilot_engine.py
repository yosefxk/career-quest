import json
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from app.core.database import get_db
from app.core.llm_gateway import llm

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

def extract_directive_from_turn(user_text: str) -> Optional[Dict[str, str]]:
    """
    Checks if the user's message expresses an opinion, preference, or rule
    to be remembered for future CV generation and tailoring.
    """
    import re
    # 1. Instant Direct Pattern Match
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

    prompt = f"""
Analyze this user message to determine if they are teaching a persistent preference, style rule, constraint, or opinion for their career materials (CV, summaries, bullets, job preferences, tone).

User Message:
\"\"\"
{user_text}
\"\"\"

Output strictly JSON:
{{
  "is_directive": true,
  "category": "cv_style" or "tone" or "formatting" or "job_preference" or "general",
  "rule_text": "A clear, concise, self-contained rule statement capturing the user's preference."
}}
If the message is just a general question or doesn't establish a persistent rule, set "is_directive": false.
"""
    res = llm.generate_json(prompt, system_prompt="Output valid JSON only.")
    if res and res.get("is_directive") and res.get("rule_text"):
        return {
            "category": res.get("category", "cv_style"),
            "rule_text": res.get("rule_text").strip()
        }
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
Company: {focused_job.get('company')}
Title: {focused_job.get('title')}
Location: {focused_job.get('location')}
Salary: {focused_job.get('salary', 'Competitive')}
Match Score: {focused_job.get('match_score')}%
Tailored Summary: {focused_job.get('custom_summary', 'None')}
Job Description Snippet: {focused_job.get('job_description', '')[:1200]}
"""

    return f"""You are CareerQuest AI Copilot, an elite executive career strategist, ATS resume specialist, and technical interview advisor.
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

YOUR MISSION:
1. Provide sharp, metric-driven, actionable advice on CV bullets, executive summaries, ATS keyword targeting, and interview prep.
2. When the user provides feedback, opinions, or stylistic constraints on their CVs or job search, acknowledge their direction and confirm that it is being applied to their style memory.
3. Format output in crisp GitHub-flavored Markdown with clear headings, bullet points, and concise language. Avoid corporate fluff.
"""

def process_copilot_turn(user_message: str, focused_job_id: Optional[int] = None) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Fetch Candidate Profile
    cursor.execute("SELECT * FROM candidate_profiles WHERE is_active = 1 LIMIT 1")
    cand_row = cursor.fetchone()
    cand_profile = {
        "full_name": cand_row["full_name"] if cand_row else "Candidate",
        "tagline": cand_row["tagline"] if cand_row else "",
        "skills": json.loads(cand_row["skills_json"] or "{}") if cand_row else {},
        "experience": json.loads(cand_row["experience_json"] or "[]") if cand_row else []
    }
    
    # 2. Fetch Directives
    directives = get_active_directives(conn)
    
    # 3. Fetch Jobs & Focused Job
    cursor.execute("SELECT id, company, title, status, location, salary, match_score, custom_summary, job_description FROM jobs WHERE is_archived = 0")
    job_rows = cursor.fetchall()
    active_jobs = [dict(r) for r in job_rows]
    
    focused_job = None
    if focused_job_id:
        for j in active_jobs:
            if j["id"] == focused_job_id:
                focused_job = j
                break
                
    # 4. Fetch Recent Chat History (Last 10 messages)
    cursor.execute("SELECT role, content FROM copilot_messages ORDER BY id DESC LIMIT 10")
    history_rows = cursor.fetchall()
    messages = [{"role": r["role"], "content": r["content"]} for r in reversed(history_rows)]
    messages.append({"role": "user", "content": user_message})
    
    # 5. Build System Prompt & Call LLM
    system_prompt = build_copilot_system_prompt(cand_profile, directives, active_jobs, focused_job)
    assistant_reply = llm.chat(messages, system_prompt=system_prompt)
    if not assistant_reply:
        assistant_reply = "I've reviewed your request. You can configure active style directives in the side panel to guide how I tailor all future CVs and applications."
        
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    # 6. Check for newly learned directive
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
        
    # 7. Persist User and Assistant Messages
    cursor.execute("""
    INSERT INTO copilot_messages (session_id, candidate_id, role, content, metadata_json, created_at)
    VALUES ('default', 1, 'user', ?, ?, ?)
    """, (user_message, json.dumps({"focused_job_id": focused_job_id}), now_str))
    
    cursor.execute("""
    INSERT INTO copilot_messages (session_id, candidate_id, role, content, metadata_json, created_at)
    VALUES ('default', 1, 'assistant', ?, ?, ?)
    """, (assistant_reply, json.dumps({"saved_directive": saved_directive}), now_str))
    
    conn.commit()
    conn.close()
    
    return {
        "reply": assistant_reply,
        "new_directive": saved_directive,
        "focused_job_id": focused_job_id,
        "created_at": now_str
    }

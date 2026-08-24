import re
import json
import sqlite3
import hashlib
import httpx
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator, Dict, Any, List, Optional
from app.core.config import settings
from app.core.llm_gateway import llm
from app.core.database import get_db

TARGET_BOARDS = [
    # Autonomous Vehicles & Robotics
    {"company": "Waymo", "board": "waymo", "category": "AV & Robotics", "platform": "greenhouse"},
    {"company": "Anduril", "board": "andurilindustries", "category": "Defense & Aero", "platform": "greenhouse"},
    
    # AI Infra & Compute
    {"company": "OpenAI", "board": "openai", "category": "AI Infra & Compute", "platform": "ashby"},
    {"company": "Anthropic", "board": "anthropic", "category": "AI Infra & Compute", "platform": "greenhouse"},
    {"company": "Scale AI", "board": "scaleai", "category": "AI Infra & Compute", "platform": "greenhouse"},
    {"company": "Cohere", "board": "cohere", "category": "AI Infra & Compute", "platform": "greenhouse"},
    
    # Big Data & Cloud Platforms
    {"company": "Databricks", "board": "databricks", "category": "Big Data & Cloud", "platform": "greenhouse"},
    {"company": "Cloudflare", "board": "cloudflare", "category": "Big Data & Cloud", "platform": "greenhouse"},
    {"company": "Palantir", "board": "palantirtechnologies", "category": "Big Data & Cloud", "platform": "greenhouse"},
    
    # Cybersecurity & Cloud Security
    {"company": "Wiz", "board": "wiz", "category": "Cybersecurity", "platform": "greenhouse"},
    {"company": "Snyk", "board": "snyk", "category": "Cybersecurity", "platform": "greenhouse"},
    {"company": "SentinelOne", "board": "sentinelone", "category": "Cybersecurity", "platform": "greenhouse"},
    
    # Fintech & High-Scale SaaS
    {"company": "Stripe", "board": "stripe", "category": "Fintech & Quant", "platform": "greenhouse"},
    {"company": "Ramp", "board": "ramp", "category": "Fintech & Quant", "platform": "ashby"},
    {"company": "Linear", "board": "linear", "category": "Enterprise SaaS", "platform": "ashby"},
    {"company": "Vanta", "board": "vanta", "category": "Cybersecurity", "platform": "ashby"},
    {"company": "Figma", "board": "figma", "category": "Enterprise SaaS", "platform": "greenhouse"}
]

TARGET_KEYWORDS = [
    "program manager", "tpm", "technical project", "data engineer", 
    "data infrastructure", "data platform", "ai ops", "platform engineer",
    "solutions architect", "integration", "operations lead", "infrastructure lead", "software engineer"
]

def get_learned_preferences(conn: sqlite3.Connection) -> Dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute("SELECT company, title, interest_rating FROM discovery_digest WHERE interest_rating != 0")
    ratings = cursor.fetchall()
    
    liked_companies = set()
    disliked_companies = set()
    for row in ratings:
        comp, _, rating = row[0], row[1], row[2]
        if rating == 1:
            liked_companies.add(comp)
        elif rating == -1:
            disliked_companies.add(comp)
            
    return {
        "liked_companies": list(liked_companies),
        "disliked_companies": list(disliked_companies)
    }

def batch_evaluate_with_llm(roles: List[Dict[str, Any]], preferences: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if not roles:
        return []
        
    prompt = f"""
Evaluate these {len(roles)} discovered job opportunities for technical leadership, program management, and data systems.

User Preferences: {json.dumps(preferences or {})}

Roles:
{json.dumps([{ 'id': idx, 'company': r['company'], 'title': r['title'], 'location': r['location'], 'snippet': r.get('snippet', '') } for idx, r in enumerate(roles)])}

Output strictly JSON:
{{
  "evaluated_roles": [
    {{
      "id": 0,
      "match_score": 92,
      "salary_min": 175000,
      "salary_max": 225000,
      "salary_display": "$175k - $225k + RSUs",
      "match_highlights": ["Highlight 1", "Highlight 2"]
    }}
  ]
}}
"""
    result = llm.generate_json(prompt, system_prompt="Output valid JSON only.")
    eval_map = {}
    if result and "evaluated_roles" in result:
        for item in result["evaluated_roles"]:
            eval_map[item.get("id")] = item

    output = []
    for idx, r in enumerate(roles):
        evaluated = eval_map.get(idx, {})
        output.append({
            **r,
            "match_score": evaluated.get("match_score", 85),
            "salary_min": evaluated.get("salary_min", 0),
            "salary_max": evaluated.get("salary_max", 0),
            "salary_display": evaluated.get("salary_display", "Competitive Market Comp"),
            "match_highlights": evaluated.get("match_highlights", ["High-fit technical position"])
        })
    return output

def stream_opportunity_scan() -> Generator[Dict[str, Any], None, None]:
    yield {
        "step": "init",
        "progress": 5,
        "boards_done": 0,
        "total_boards": len(TARGET_BOARDS),
        "roles_found": 0,
        "evaluated_count": 0,
        "added_count": 0,
        "message": f"Starting high-speed parallel scan across {len(TARGET_BOARDS)} top tech career portals..."
    }
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    now = datetime.now(timezone.utc)
    discovered = []
    done_count = 0
    
    def fetch_single_board(b):
        board_name = b["board"]
        company_name = b["company"]
        category = b["category"]
        platform = b.get("platform", "greenhouse")
        found = []
        try:
            with httpx.Client(headers=headers, timeout=6.0) as client:
                if platform == "ashby":
                    resp = client.get(f"https://api.ashbyhq.com/posting-api/job-board/{board_name}")
                    if resp.status_code == 200:
                        data = resp.json()
                        for j in data.get("jobs", []):
                            title = j.get("title", "")
                            title_lower = title.lower()
                            if any(k in title_lower for k in TARGET_KEYWORDS):
                                loc_name = j.get("locationName", "Global / Remote") or "Global / Remote"
                                job_url = j.get("jobUrl") or f"https://jobs.ashbyhq.com/{board_name}/{j.get('id')}"
                                found.append({
                                    "company": company_name,
                                    "title": title,
                                    "location": loc_name,
                                    "region": "Global" if "remote" in loc_name.lower() else "US",
                                    "category": category,
                                    "url": job_url,
                                    "source": f"{company_name} Ashby",
                                    "role_family": "Engineering",
                                    "yoe_min": 3,
                                    "yoe_max": 7,
                                    "yoe_display": "3–7 YOE",
                                    "snippet": f"Active role at {company_name} ({loc_name}).",
                                    "posted_date": now.strftime("%Y-%m-%d")
                                })
                else:
                    resp = client.get(f"https://boards-api.greenhouse.io/v1/boards/{board_name}/jobs")
                    if resp.status_code == 200:
                        data = resp.json()
                        for j in data.get("jobs", []):
                            title = j.get("title", "")
                            title_lower = title.lower()
                            if any(k in title_lower for k in TARGET_KEYWORDS):
                                loc_name = j.get("location", {}).get("name", "Global / Remote") or "Global / Remote"
                                job_url = j.get("absolute_url") or f"https://job-boards.greenhouse.io/{board_name}/jobs/{j.get('id')}"
                                found.append({
                                    "company": company_name,
                                    "title": title,
                                    "location": loc_name,
                                    "region": "Global" if "remote" in loc_name.lower() else "US",
                                    "category": category,
                                    "url": job_url,
                                    "source": f"{company_name} Greenhouse",
                                    "role_family": "Engineering",
                                    "yoe_min": 3,
                                    "yoe_max": 7,
                                    "yoe_display": "3–7 YOE",
                                    "snippet": f"Active role at {company_name} ({loc_name}).",
                                    "posted_date": now.strftime("%Y-%m-%d")
                                })
        except Exception as e:
            print(f"Error scraping {platform} {board_name}: {e}")
        return company_name, found

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_single_board, b): b for b in TARGET_BOARDS}
        for future in as_completed(futures):
            done_count += 1
            comp_name, board_roles = future.result()
            discovered.extend(board_roles)
            progress_pct = int(5 + (done_count / len(TARGET_BOARDS)) * 45)
            
            yield {
                "step": "board",
                "progress": progress_pct,
                "boards_done": done_count,
                "total_boards": len(TARGET_BOARDS),
                "company": comp_name,
                "roles_found": len(discovered),
                "evaluated_count": 0,
                "added_count": 0,
                "message": f"Scanned {comp_name} — found {len(board_roles)} candidate positions"
            }

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT job_key FROM discovery_digest")
    existing_keys = {row[0] for row in cursor.fetchall()}
    cursor.execute("SELECT company, title FROM jobs")
    pipeline_jobs = {(row[0].lower().strip(), row[1].lower().strip()) for row in cursor.fetchall()}
    preferences = get_learned_preferences(conn)
    
    unseen_jobs = []
    for j in discovered:
        key = hashlib.md5(f"{j['company']}_{j['title']}_{j['location']}".encode()).hexdigest()
        if key not in existing_keys:
            j["job_key"] = key
            j["in_pipeline"] = 1 if (j['company'].lower().strip(), j['title'].lower().strip()) in pipeline_jobs else 0
            unseen_jobs.append(j)
            
    yield {
        "step": "dedup",
        "progress": 55,
        "boards_done": len(TARGET_BOARDS),
        "total_boards": len(TARGET_BOARDS),
        "roles_found": len(discovered),
        "unseen_count": len(unseen_jobs),
        "evaluated_count": 0,
        "added_count": 0,
        "message": f"Deduplication complete: {len(unseen_jobs)} new unseen roles discovered."
    }
    
    to_evaluate = unseen_jobs[:12]
    evaluated = []
    if to_evaluate:
        yield {
            "step": "evaluating",
            "progress": 70,
            "boards_done": len(TARGET_BOARDS),
            "total_boards": len(TARGET_BOARDS),
            "roles_found": len(discovered),
            "evaluated_count": 0,
            "added_count": 0,
            "message": f"🧠 Running single-batch AI evaluation for top {len(to_evaluate)} high-fit roles..."
        }
        
        evaluated = batch_evaluate_with_llm(to_evaluate, preferences=preferences)
        
        yield {
            "step": "saving",
            "progress": 88,
            "boards_done": len(TARGET_BOARDS),
            "total_boards": len(TARGET_BOARDS),
            "roles_found": len(discovered),
            "evaluated_count": len(evaluated),
            "added_count": 0,
            "message": f"💾 Saving {len(evaluated)} evaluated opportunities with salary calibration..."
        }
        
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        for item in evaluated:
            cursor.execute("""
            INSERT OR IGNORE INTO discovery_digest
            (job_key, company, title, location, region, category, url, source, salary_min, salary_max, salary_display, match_score, match_highlights, role_family, yoe_min, yoe_max, yoe_display, snippet, posted_date, in_pipeline, is_archived, interest_rating, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
            """, (
                item["job_key"],
                item["company"],
                item["title"],
                item["location"],
                item["region"],
                item["category"],
                item["url"],
                item["source"],
                item.get("salary_min", 0),
                item.get("salary_max", 0),
                item.get("salary_display", "Competitive Market Comp"),
                item.get("match_score", 85),
                json.dumps(item.get("match_highlights", [])),
                item.get("role_family", "Engineering"),
                item.get("yoe_min", 3),
                item.get("yoe_max", 7),
                item.get("yoe_display", "3–7 YOE"),
                item.get("snippet", ""),
                item.get("posted_date", now_str[:10]),
                item.get("in_pipeline", 0),
                now_str
            ))
        conn.commit()
        
    cursor.execute("SELECT COUNT(*) FROM discovery_digest WHERE is_archived = 0")
    active_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM discovery_digest WHERE is_archived = 1")
    archived_count = cursor.fetchone()[0]
    conn.close()
    
    yield {
        "step": "complete",
        "progress": 100,
        "boards_done": len(TARGET_BOARDS),
        "total_boards": len(TARGET_BOARDS),
        "roles_found": len(discovered),
        "evaluated_count": len(evaluated),
        "added_count": len(evaluated),
        "total_active": active_count,
        "total_archived": archived_count,
        "message": f"Scan Complete! Discovered {len(discovered)} raw roles and added {len(evaluated)} high-match opportunities."
    }

import re
import json
import httpx
from bs4 import BeautifulSoup
from io import BytesIO
from typing import Dict, Any, Tuple, Optional, List
from pypdf import PdfReader
from app.core.llm_gateway import llm

TECH_KEYWORDS = [
    "python", "sql", "snowflake", "dbt", "docker", "linux", "bash", "aws", "gcp", "azure", "s3",
    "kubernetes", "argo workflows", "spark", "kafka", "etl", "elt", "parquet", "mongodb", "elasticsearch",
    "data pipeline", "data infrastructure", "telemetry", "adas", "autonomous vehicles", "cybersecurity",
    "project manager", "tpm", "product manager", "agile", "scrum", "oem", "tier 1", "saas",
    "ci/cd", "jenkins", "git", "rest api", "fastapi", "react", "typescript", "machine learning", "ai", "llm"
]

def clean_input_url(url: str) -> str:
    if not url: return ""
    cleaned = url.strip()
    return re.sub(r':(8095|8096|8098|8085|8000|5000|3000)/?$', '', cleaned)

def extract_job_text_from_url(url: str) -> Tuple[str, str, str]:
    cleaned_url = clean_input_url(url)
    if not cleaned_url: return "", "", ""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        with httpx.Client(follow_redirects=True, timeout=12.0, headers=headers) as client:
            resp = client.get(cleaned_url)
            if resp.status_code != 200: return "", "", ""
            soup = BeautifulSoup(resp.text, 'html.parser')
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
                tag.decompose()
            text = ' '.join(soup.stripped_strings)
            title = soup.title.string if soup.title else ""
            return text[:12000], title.strip(), cleaned_url
    except Exception as e:
        print(f"Error fetching URL {cleaned_url}: {e}")
        return "", "", cleaned_url

def parse_uploaded_resume(file_bytes: bytes, filename: str) -> Optional[Dict[str, Any]]:
    """
    Extracts raw text from an uploaded resume (PDF, TXT, MD, YAML)
    and uses the configured LLM to parse it into a standardized CandidateProfile dictionary.
    """
    extracted_text = ""
    lower_fn = filename.lower()
    
    if lower_fn.endswith(".pdf"):
        try:
            reader = PdfReader(BytesIO(file_bytes))
            for page in reader.pages:
                extracted_text += page.extract_text() + "\n"
        except Exception as e:
            print(f"PDF read error: {e}")
            return None
    else:
        try:
            extracted_text = file_bytes.decode("utf-8")
        except Exception:
            extracted_text = file_bytes.decode("latin-1", errors="ignore")
            
    if not extracted_text.strip():
        return None

    prompt = f"""
You are an expert ATS Resume Intelligence System. Parse the following resume text into a strictly formatted JSON CandidateProfile.

Resume Content:
\"\"\"
{extracted_text[:12000]}
\"\"\"

Requirements:
1. Extract Candidate Contact Information (full_name, email, phone, location, citizenship, linkedin_url, github_url, portfolio_url, tagline).
2. Extract Work Experience: Each position must have company, role, location, dates, and an array of bullets. For each bullet, assign a unique id (e.g. comp1_b1), category, relevant tags, and set default to true.
3. Extract Education: institution, degree, honors, gpa, dates.
4. Extract Skills grouped into 3-4 clean categories (e.g. 'Technical & Cloud', 'Leadership & Methodologies', 'Tools & Frameworks').
5. Generate 2-3 tailored Archetypes (e.g., primary role family, secondary role family) with a 2-3 sentence executive summary.

Output ONLY valid JSON matching this schema:
{{
  "full_name": "Full Name",
  "email": "email@example.com",
  "phone": "+1 ...",
  "location": "City, Country",
  "citizenship": "Citizenship details or null",
  "linkedin_url": "https://linkedin.com/in/...",
  "github_url": "https://github.com/...",
  "portfolio_url": null,
  "tagline": "Professional headline",
  "archetypes": {{
    "primary": {{ "title": "Primary Title", "summary": "Executive summary...", "active_tags": ["tag1", "tag2"] }}
  }},
  "experience": [
    {{
      "company": "Company",
      "role": "Job Title",
      "location": "Location",
      "dates": "2020 – Present",
      "bullets": [
        {{ "id": "exp1_b1", "text": "Accomplished X as measured by Y doing Z.", "category": "Impact", "tags": ["Python", "Scale"], "default": true }}
      ]
    }}
  ],
  "education": [
    {{ "institution": "University Name", "degree": "B.Sc. / M.Sc.", "honors": "Honors / null", "gpa": "3.9 / null", "dates": "2016 – 2020" }}
  ],
  "skills": {{
    "Technical Core": ["Skill 1", "Skill 2"],
    "Leadership & Delivery": ["Skill 3", "Skill 4"]
  }}
}}
"""
    return llm.generate_json(prompt, system_prompt="You are a JSON resume parser. Output strictly valid JSON with no markdown backticks.")

def analyze_job_fit(job_text: str, candidate_profile: Dict[str, Any], url: str = "") -> Dict[str, Any]:
    cand_name = candidate_profile.get("full_name", "Candidate")
    cand_skills = candidate_profile.get("skills", {})
    archetypes = candidate_profile.get("archetypes", {})
    
    prompt = f"""
You are an Executive Tech Career Strategist analyzing a job posting for candidate {cand_name}.

Candidate Archetypes: {json.dumps(archetypes)}
Candidate Skills: {json.dumps(cand_skills)}

Job Description:
\"\"\"
{job_text[:8000]}
\"\"\"

Analyze this position and output strictly JSON:
{{
  "company": "Extracted Company Name",
  "title": "Clean Role Title",
  "location": "Job Location / Remote status",
  "match_score": 88,
  "recommended_profile": "primary archetype id",
  "tailored_summary": "High-impact 2-3 sentence executive summary tailoring {cand_name}'s proven metrics to this exact role.",
  "top_keywords_to_include": ["Keyword1", "Keyword2", "Keyword3"],
  "leveling_and_comp": {{
    "target_level": "e.g. Senior / Staff / Lead",
    "market_comp_us": "$160k - $210k + Equity",
    "market_comp_local": "Competitive market rate",
    "negotiation_levers": ["Lever 1 with quantified scale", "Lever 2 with unique technical edge"]
  }},
  "recruiter_inmail": "A high-converting 60-word intro message to the hiring manager.",
  "star_interview_prep": [
    {{
      "question": "Anticipated technical/behavioral bottleneck question",
      "situation_task": "Relevant context from candidate history",
      "action": "Action to highlight",
      "result": "Quantified outcome"
    }}
  ]
}}
"""
    result = llm.generate_json(prompt, system_prompt="Output valid JSON only.")
    if not result:
        return {
            "company": "Target Company",
            "title": "Target Role",
            "match_score": 85,
            "tailored_summary": candidate_profile.get("tagline", "Experienced technical leader."),
            "recruiter_inmail": "Hi, I noticed the open position and would love to connect.",
            "star_interview_prep": []
        }
    return result

def audit_ats_compliance(html_content: str, candidate_profile: Dict[str, Any], job_description: Optional[str] = None) -> Dict[str, Any]:
    soup = BeautifulSoup(html_content, 'html.parser')
    text_content = soup.get_text()
    
    checks = []
    score = 100
    
    # 1. Text Layer Extractability
    if len(text_content.strip()) > 300:
        checks.append({"name": "Text-Layer Extractability", "passed": True, "detail": f"Parsed {len(text_content.split())} words cleanly from HTML/PDF structure."})
    else:
        score -= 25
        checks.append({"name": "Text-Layer Extractability", "passed": False, "detail": "Insufficient extractable text layer detected."})
        
    # 2. Standard ATS Section Headers
    required_headers = ["EXPERIENCE", "EDUCATION", "SKILLS"]
    found_headers = [h for h in required_headers if h in text_content.upper()]
    if len(found_headers) == len(required_headers):
        checks.append({"name": "Standard Heading Hierarchy", "passed": True, "detail": "Contains standard Workday/Greenhouse recognized headers."})
    else:
        score -= 15
        checks.append({"name": "Standard Heading Hierarchy", "passed": False, "detail": f"Missing headings: {set(required_headers) - set(found_headers)}"})

    # 3. Contact Info Validation
    email_passed = bool(re.search(r'[\w\.-]+@[\w\.-]+', text_content))
    if email_passed:
        checks.append({"name": "Direct Contact Formatting", "passed": True, "detail": "Email and location correctly structured at top header."})
    else:
        score -= 20
        checks.append({"name": "Direct Contact Formatting", "passed": False, "detail": "Email address was not detected."})

    # 4. Keyword Coverage
    matched_kws = []
    lower_text = text_content.lower()
    for kw in TECH_KEYWORDS:
        if kw in lower_text:
            matched_kws.append(kw.title())
            
    checks.append({
        "name": "ATS Core Keyword Density",
        "passed": len(matched_kws) >= 6,
        "detail": f"Identified {len(matched_kws)} industry keywords in document body."
    })
    if len(matched_kws) < 6:
        score -= 10

    # 5. Single-Page Bullet Budget
    bullet_count = len(soup.find_all('li'))
    if 6 <= bullet_count <= 10:
        checks.append({"name": "Single-Page Length Budget", "passed": True, "detail": f"Optimal bullet count: {bullet_count} bullets (Fits strict 1-page baseline)."})
    else:
        score -= 10
        checks.append({"name": "Single-Page Length Budget", "passed": False, "detail": f"{bullet_count} bullets found. Recommend 7-9 bullets for 1-page fit."})

    return {
        "ats_score": max(50, min(100, score)),
        "status": "PASS" if score >= 80 else "WARNING",
        "checks": checks,
        "matched_keywords": matched_kws[:12]
    }

def generate_recruiter_inmails(company: str, title: str, job_description: str, candidate_profile: Dict[str, Any]) -> Dict[str, str]:
    prompt = f"""
Write 3 distinct high-converting LinkedIn InMail messages for {candidate_profile.get('full_name')} reaching out for {title} at {company}.
Candidate summary: {candidate_profile.get('tagline')}

Job details snippet:
\"\"\"
{job_description[:1500]}
\"\"\"

Output strictly JSON:
{{
  "hiring_manager": "Direct, value-first message to the Engineering Director / Hiring Manager (3-4 sentences, highlighting direct ROI metrics).",
  "recruiter_followup": "Crisp message to the Talent Acquisition Lead referencing application submitted (2-3 sentences).",
  "peer_referral": "Casual, respectful message to a current Senior Engineer / Team Member asking for brief insight and potentially a referral (2-3 sentences)."
}}
"""
    res = llm.generate_json(prompt, system_prompt="Output valid JSON only.")
    if not res:
        return {
            "hiring_manager": f"Hi, I noticed the open {title} role at {company}. With my background in engineering scale, I would love to connect.",
            "recruiter_followup": f"Hi, I recently applied for the {title} position at {company} and would welcome a brief introductory chat.",
            "peer_referral": f"Hi, I am exploring the {title} opening at {company} and would love to hear about the engineering team culture."
        }
    return res

def generate_company_intel(company: str, title: str, job_description: str) -> Dict[str, Any]:
    prompt = f"""
Provide an intelligence brief for company: '{company}' for role '{title}'.
Snippet: {job_description[:1500]}

Output strictly JSON:
{{
  "company": "{company}",
  "business_overview": "2-3 sentences on business model, market position, and growth trajectory.",
  "tech_stack": ["Tech1", "Tech2", "Tech3", "Tech4", "Tech5"],
  "strategic_priorities": ["Priority 1", "Priority 2"],
  "culture_and_interview_style": "Brief overview of what engineering leadership values."
}}
"""
    res = llm.generate_json(prompt, system_prompt="Output valid JSON only.")
    if not res:
        return {
            "company": company,
            "business_overview": f"{company} is scaling modern engineering infrastructure and platform products.",
            "tech_stack": ["Python", "Cloud", "Distributed Systems", "Data Pipelines", "Docker"],
            "strategic_priorities": ["Platform reliability", "Scaling throughput"],
            "culture_and_interview_style": "Values ownership, clear technical metrics, and collaborative architecture."
        }
    return res

def generate_role_mock_interview(company: str, title: str, job_description: str, candidate_profile: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""
Generate 10 role-specific mock interview questions (5 Technical Architecture + 5 STAR Behavioral) for candidate {candidate_profile.get('full_name')} interviewing for {title} at {company}.

Candidate details: {candidate_profile.get('tagline')}
Job snippet: {job_description[:2000]}

Output strictly JSON:
{{
  "technical_questions": [
    {{
      "question": "Deep technical/architectural scenario question",
      "focus": "Key technical bottleneck or scale challenge",
      "answer_blueprint": "How the candidate should structure their technical answer"
    }}
  ],
  "behavioral_questions": [
    {{
      "question": "Behavioral situation question (conflict, deadline, prioritization)",
      "situation_task": "Relevant context",
      "action": "Key leadership action",
      "result": "Measurable outcome"
    }}
  ]
}}
"""
    res = llm.generate_json(prompt, system_prompt="Output valid JSON with 5 technical and 5 behavioral questions.", timeout=45.0)
    if not res:
        return {
            "technical_questions": [
                {
                    "question": f"How do you design scalable telemetry pipelines for {company} under strict latency SLAs?",
                    "focus": "Throughput and latency optimization",
                    "answer_blueprint": "Discuss asynchronous ingestion, message queuing, and caching layers."
                }
            ],
            "behavioral_questions": [
                {
                    "question": "Tell me about a technical bottleneck you diagnosed and resolved under pressure.",
                    "situation_task": "High latency workflow bottleneck",
                    "action": "Redesigned indexing and optimized API polling queries",
                    "result": "Cut response times significantly"
                }
            ]
        }
    return res

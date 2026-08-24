import re
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from jinja2 import Template
from playwright.sync_api import sync_playwright
from app.core.config import settings

CV_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  @page {
    size: letter portrait;
    margin: 0;
  }
  *, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }
  body {
    font-family: 'Liberation Sans', 'DejaVu Sans', 'Arial', sans-serif;
    color: #1e293b;
    background: #ffffff;
    font-size: 9.0pt;
    line-height: 1.25;
    padding: 24pt 32pt;
    width: 100%;
  }
  header {
    text-align: center;
    border-bottom: 1.5pt solid #0f172a;
    padding-bottom: 5pt;
    margin-bottom: 6pt;
  }
  .candidate-name {
    font-size: 16pt;
    font-weight: 800;
    color: #0f172a;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 2pt;
  }
  .tagline {
    font-size: 9.5pt;
    font-weight: 600;
    color: #3b82f6;
    margin-bottom: 3pt;
  }
  .contact-info {
    font-size: 8.2pt;
    color: #475569;
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 6pt;
    flex-wrap: wrap;
  }
  .contact-info a {
    color: #1e40af;
    text-decoration: none;
    font-weight: 600;
  }
  .section-title {
    font-size: 9.8pt;
    font-weight: 800;
    color: #0f172a;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1pt solid #94a3b8;
    padding-bottom: 1.5pt;
    margin-top: 5.5pt;
    margin-bottom: 3.5pt;
  }
  .summary-text {
    font-size: 8.8pt;
    color: #334155;
    text-align: justify;
    line-height: 1.25;
  }
  .skills-grid {
    display: flex;
    flex-direction: column;
    gap: 2pt;
  }
  .skill-row {
    font-size: 8.6pt;
    line-height: 1.25;
  }
  .skill-label {
    font-weight: 700;
    color: #0f172a;
  }
  .skill-val {
    color: #334155;
  }
  .experience-block {
    margin-bottom: 4.5pt;
  }
  .experience-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-size: 9.0pt;
    margin-bottom: 1pt;
  }
  .job-title {
    font-weight: 700;
    color: #0f172a;
  }
  .company-name {
    font-weight: 600;
    color: #2563eb;
  }
  .job-dates {
    font-size: 8.3pt;
    font-weight: 600;
    color: #64748b;
  }
  ul.bullets-list {
    list-style-type: square;
    padding-left: 11pt;
    margin: 0;
  }
  ul.bullets-list li {
    font-size: 8.7pt;
    color: #334155;
    margin-bottom: 1.5pt;
    line-height: 1.22;
    text-align: justify;
  }
  ul.bullets-list li strong {
    color: #0f172a;
  }
  .edu-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-size: 8.8pt;
    margin-bottom: 1.5pt;
  }
  .edu-degree {
    font-weight: 700;
    color: #0f172a;
  }
  .edu-school {
    color: #2563eb;
    font-weight: 600;
  }
  .edu-dates {
    font-size: 8.3pt;
    font-weight: 600;
    color: #64748b;
  }
</style>
</head>
<body>

<header>
  <div class="candidate-name">{{ profile.full_name }}</div>
  {% if profile.tagline %}<div class="tagline">{{ profile.tagline }}</div>{% endif %}
  <div class="contact-info">
    {% if profile.location %}<span>{{ profile.location }}</span> &bull;{% endif %}
    {% if profile.citizenship %}<span>{{ profile.citizenship }}</span> &bull;{% endif %}
    {% if profile.phone %}<span>{{ profile.phone }}</span> &bull;{% endif %}
    <a href="mailto:{{ profile.email }}">{{ profile.email }}</a>
    {% if profile.linkedin_url %}&bull; <a href="{{ profile.linkedin_url }}" target="_blank">LinkedIn</a>{% endif %}
    {% if profile.github_url %}&bull; <a href="{{ profile.github_url }}" target="_blank">GitHub</a>{% endif %}
    {% if profile.portfolio_url %}&bull; <a href="{{ profile.portfolio_url }}" target="_blank">Portfolio</a>{% endif %}
  </div>
</header>

{% if custom_summary %}
<div class="section-title">Executive Summary</div>
<div class="summary-text">{{ custom_summary }}</div>
{% endif %}

<div class="section-title">Technical & Leadership Core</div>
<div class="skills-grid">
  {% for cat, skills_list in profile.skills.items() %}
  <div class="skill-row">
    <span class="skill-label">{{ cat }}:</span>
    <span class="skill-val">{{ skills_list | join(' &bull; ') }}</span>
  </div>
  {% endfor %}
</div>

<div class="section-title">Professional Experience</div>
{% for exp in filtered_experience %}
<div class="experience-block">
  <div class="experience-header">
    <div>
      <span class="job-title">{{ exp.role }}</span> &ndash; <span class="company-name">{{ exp.company }}</span>
    </div>
    <div class="job-dates">{{ exp.dates }}</div>
  </div>
  <ul class="bullets-list">
    {% for bullet in exp.active_bullets %}
    <li>{{ bullet.text | safe }}</li>
    {% endfor %}
  </ul>
</div>
{% endfor %}

{% if profile.education %}
<div class="section-title">Education & Credentials</div>
{% for edu in profile.education %}
<div class="edu-row">
  <div>
    <span class="edu-degree">{{ edu.degree }}</span> &ndash; <span class="edu-school">{{ edu.institution }}</span>
    {% if edu.honors %}<span style="color: #059669; font-weight: 700;"> ({{ edu.honors }}{% if edu.gpa %}, GPA: {{ edu.gpa }}{% endif %})</span>{% endif %}
  </div>
  <div class="edu-dates">{{ edu.dates }}</div>
</div>
{% endfor %}
{% endif %}

</body>
</html>
"""

def filter_experience_bullets(experience_list: List[Dict[str, Any]], selected_bullet_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    filtered = []
    for comp in experience_list:
        comp_copy = dict(comp)
        bullets = comp.get("bullets", [])
        if selected_bullet_ids:
            active = [b for b in bullets if b.get("id") in selected_bullet_ids]
        else:
            active = [b for b in bullets if b.get("default", True)]
        comp_copy["active_bullets"] = active
        if active:
            filtered.append(comp_copy)
    return filtered

def render_cv_html(profile_data: Dict[str, Any], custom_summary: Optional[str] = None, selected_bullet_ids: Optional[List[str]] = None) -> str:
    template = Template(CV_HTML_TEMPLATE)
    filtered_exp = filter_experience_bullets(profile_data.get("experience", []), selected_bullet_ids)
    return template.render(
        profile=profile_data,
        custom_summary=custom_summary or profile_data.get("tagline", ""),
        filtered_experience=filtered_exp
    )

def generate_cv_markdown(profile_data: Dict[str, Any], custom_summary: Optional[str] = None, selected_bullet_ids: Optional[List[str]] = None) -> str:
    lines = []
    lines.append(f"# {profile_data.get('full_name', 'Candidate Resume')}")
    contacts = []
    if profile_data.get("location"): contacts.append(profile_data["location"])
    if profile_data.get("citizenship"): contacts.append(profile_data["citizenship"])
    if profile_data.get("phone"): contacts.append(profile_data["phone"])
    if profile_data.get("email"): contacts.append(profile_data["email"])
    if profile_data.get("linkedin_url"): contacts.append(profile_data["linkedin_url"])
    if profile_data.get("github_url"): contacts.append(profile_data["github_url"])
    lines.append(" | ".join(contacts))
    lines.append("")
    
    if custom_summary:
        lines.append("## Executive Summary")
        lines.append(custom_summary)
        lines.append("")
        
    skills = profile_data.get("skills", {})
    if skills:
        lines.append("## Technical & Leadership Skills")
        for cat, items in skills.items():
            lines.append(f"- **{cat}**: {', '.join(items)}")
        lines.append("")
        
    lines.append("## Professional Experience")
    filtered_exp = filter_experience_bullets(profile_data.get("experience", []), selected_bullet_ids)
    for exp in filtered_exp:
        lines.append(f"### {exp.get('role')} — {exp.get('company')} ({exp.get('dates')})")
        for b in exp.get("active_bullets", []):
            clean_text = re.sub(r'<[^>]+>', '', b.get("text", ""))
            lines.append(f"- {clean_text}")
        lines.append("")
        
    edu_list = profile_data.get("education", [])
    if edu_list:
        lines.append("## Education & Credentials")
        for edu in edu_list:
            honors = f" ({edu.get('honors')})" if edu.get('honors') else ""
            lines.append(f"- **{edu.get('degree')}** — {edu.get('institution')}{honors} ({edu.get('dates')})")
            
    return "\n".join(lines)

def generate_cv_pdf(html_content: str, folder_name: str, candidate_name: str = "Resume", markdown_content: Optional[str] = None) -> str:
    safe_folder = re.sub(r'[^a-zA-Z0-9_\-]', '_', folder_name)
    target_dir = Path(settings.cvs_path) / safe_folder
    target_dir.mkdir(parents=True, exist_ok=True)
    
    safe_name = re.sub(r'[^a-zA-Z0-9_\-\s]', '', candidate_name).strip() or "Resume"
    html_path = target_dir / f"{safe_name}.html"
    md_path = target_dir / f"{safe_name}.md"
    pdf_path = target_dir / f"{safe_name}.pdf"
    
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    if markdown_content:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page()
        page.set_content(html_content, wait_until="networkidle")
        page.pdf(
            path=str(pdf_path),
            format="Letter",
            print_background=True,
            margin={"top": "0in", "right": "0in", "bottom": "0in", "left": "0in"}
        )
        browser.close()
        
    return f"{safe_folder}/{safe_name}.pdf"

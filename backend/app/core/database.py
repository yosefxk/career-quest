import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from app.core.config import settings

def get_db():
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    """Initializes all database tables with support for multiple candidates and dynamic profiles."""
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Candidate Master Profiles
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS candidate_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        is_active INTEGER DEFAULT 1,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT,
        location TEXT,
        citizenship TEXT,
        linkedin_url TEXT,
        github_url TEXT,
        portfolio_url TEXT,
        tagline TEXT,
        archetypes_json TEXT,          -- JSON of { archetype_id: { title, summary, skills_summary, active_tags } }
        experience_json TEXT,          -- JSON of [ { company, role, location, dates, bullets: [ { id, text, category, tags, default } ] } ]
        education_json TEXT,           -- JSON of [ { institution, degree, honors, gpa, dates, details } ]
        skills_json TEXT,              -- JSON of { category_name: [skill1, skill2] }
        preferences_json TEXT,         -- JSON of { target_roles, target_locations, target_seniority, include_linkedin }
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # Safe migration for existing databases
    cursor.execute("PRAGMA table_info(candidate_profiles)")
    cols = [r[1] for r in cursor.fetchall()]
    if "preferences_json" not in cols:
        try:
            cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN preferences_json TEXT")
        except Exception:
            pass

    # 2. Pipeline Applications (Kanban)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER DEFAULT 1,
        company TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT,
        location TEXT,
        salary TEXT,
        status TEXT DEFAULT 'wishlist',  -- wishlist, tailoring, applied, screen, technical, onsite, offer, archived
        match_score INTEGER DEFAULT 85,
        job_description TEXT,
        analysis_data TEXT,             -- JSON breakdown from LLM
        tailored_profile TEXT DEFAULT 'default',
        custom_summary TEXT,
        selected_bullets_json TEXT,     -- JSON array of selected bullet IDs
        notes TEXT,
        cv_pdf_filename TEXT,
        is_archived INTEGER DEFAULT 0,
        interest_rating INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (candidate_id) REFERENCES candidate_profiles (id)
    )
    """)

    # 3. Discovery Digest (Multi-Platform Parallel Scraped Roles)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS discovery_digest (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_key TEXT UNIQUE,
        company TEXT NOT NULL,
        title TEXT NOT NULL,
        location TEXT,
        region TEXT DEFAULT 'Global',
        category TEXT DEFAULT 'Tech',
        url TEXT NOT NULL,
        source TEXT,
        salary_min INTEGER DEFAULT 0,
        salary_max INTEGER DEFAULT 0,
        salary_display TEXT,
        match_score INTEGER DEFAULT 85,
        match_highlights TEXT,
        role_family TEXT DEFAULT 'Engineering',
        yoe_min INTEGER DEFAULT 0,
        yoe_max INTEGER DEFAULT 10,
        yoe_display TEXT,
        snippet TEXT,
        posted_date TEXT,
        in_pipeline INTEGER DEFAULT 0,
        is_archived INTEGER DEFAULT 0,
        interest_rating INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)

    # 4. Application Snapshots Vault (Immutable submission history)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS application_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        candidate_id INTEGER DEFAULT 1,
        company TEXT NOT NULL,
        title TEXT NOT NULL,
        stage TEXT NOT NULL,
        summary_text TEXT,
        selected_bullets TEXT,
        markdown_content TEXT,
        pdf_filename TEXT,
        job_description TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (job_id) REFERENCES jobs (id),
        FOREIGN KEY (candidate_id) REFERENCES candidate_profiles (id)
    )
    """)

    # 5. Target Companies Radar
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS target_companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        industry TEXT,
        careers_url TEXT,
        priority TEXT DEFAULT 'high',
        notes TEXT,
        region TEXT DEFAULT 'Global',
        category TEXT DEFAULT 'Tech',
        created_at TEXT NOT NULL
    )
    """)

    # 6. User Preferences & Filter Memory
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # 7. User Directives & Style Guidance (Taught Opinions & Rules)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_directives (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER DEFAULT 1,
        category TEXT DEFAULT 'cv_style', -- 'cv_style', 'tone', 'formatting', 'job_preference', 'general'
        rule_text TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        source TEXT DEFAULT 'chat',      -- 'chat' or 'manual'
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # 8. Copilot Multi-Turn Chat Messages
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS copilot_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT DEFAULT 'default',
        candidate_id INTEGER DEFAULT 1,
        role TEXT NOT NULL,              -- 'user', 'assistant', 'system'
        content TEXT NOT NULL,
        metadata_json TEXT,              -- JSON for attached job_id, actions, extracted directive IDs
        created_at TEXT NOT NULL
    )
    """)

    conn.commit()
    seed_default_profile_if_empty(conn)
    seed_default_directives_if_empty(conn)
    conn.close()

def seed_default_profile_if_empty(conn):
    """If no candidate profile exists, seeds an initial profile template."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM candidate_profiles")
    if cursor.fetchone()[0] == 0:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        default_archetypes = {
            "primary": {
                "title": "Senior Technology Professional",
                "summary": "Experienced technology professional with a proven track record of architectural leadership, high-impact system delivery, and cross-functional team collaboration.",
                "active_tags": ["Architecture", "Engineering", "Delivery"]
            },
            "specialist": {
                "title": "Technical Specialist",
                "summary": "Specialist with deep domain expertise in designing, implementing, and scaling reliable software, cloud, and distributed architectures.",
                "active_tags": ["System Design", "Optimization", "Scale"]
            }
        }

        default_skills = {
            "Core Technologies": ["Software Architecture", "API Design", "Distributed Systems", "Cloud Platforms", "Data Engineering"],
            "Leadership & Delivery": ["Technical Leadership", "Agile/Scrum Delivery", "Cross-Functional Collaboration", "System Design Reviews"],
            "Infrastructure & Tools": ["Git", "Docker", "Linux", "CI/CD", "Observability & Monitoring", "Automated Testing"]
        }

        cursor.execute("""
        INSERT INTO candidate_profiles (
            is_active, full_name, email, phone, location, citizenship, linkedin_url, github_url, portfolio_url, tagline,
            archetypes_json, experience_json, education_json, skills_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            1,
            "Alex Morgan",
            "alex.morgan@example.com",
            "+1 (555) 019-2834",
            "Global / Remote",
            "Authorized to work globally",
            "https://linkedin.com/in/alexmorgan",
            "https://github.com/alexmorgan",
            "https://alexmorgan.dev",
            "Senior Technology Leader & Software Architect",
            json.dumps(default_archetypes),
            json.dumps([]),
            json.dumps([]),
            json.dumps(default_skills),
            now,
            now
        ))
        conn.commit()

def seed_default_directives_if_empty(conn):
    """Initializes standard best-practice career directives if none exist."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM user_directives")
    if cursor.fetchone()[0] == 0:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        initial_directives = [
            ("cv_style", "Lead resume bullets with strong active verbs and quantify business impact in USD, latency reduction, or percentage scale.", "manual"),
            ("formatting", "Strictly enforce a clean 1-page resume budget with 7 to 9 high-impact bullets across career history.", "manual"),
            ("tone", "Avoid generic corporate filler phrases like 'responsible for' or 'participated in'; emphasize leadership, engineering ownership, and architecture.", "manual"),
            ("cv_style", "Ensure tailored executive summaries directly cite target role requirements and align technical achievements to the company mission.", "manual")
        ]
        for cat, text, src in initial_directives:
            cursor.execute("""
            INSERT INTO user_directives (candidate_id, category, rule_text, is_active, source, created_at, updated_at)
            VALUES (1, ?, ?, 1, ?, ?, ?)
            """, (cat, text, src, now, now))
        conn.commit()

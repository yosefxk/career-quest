import io
import json
from pathlib import Path
import pytest
from app.core.config import settings
from app.engines.job_analyzer import analyze_job_fit, is_safe_job_url, extract_text_from_file_bytes
from app.engines.cv_renderer import render_cv_html
from app.routers.profile import backup_profile_to_file, MAX_UPLOAD_SIZE
from app.core.database import get_db, get_db_session, normalize_existing_digest_rows
from app.routers.tailor import get_master_cv_path
from app.models.digest import ScanStartRequest

def test_finding_7_analyze_job_fit_keywords():
    cand_profile = {
        "full_name": "Test Candidate",
        "tagline": "Senior Engineer",
        "skills": {"Languages": ["Python"]},
        "archetypes": {}
    }
    # Should accept pref_title, pref_company, and arbitrary kwargs without raising TypeError
    result = analyze_job_fit(
        "Senior Cloud Architect required with AWS expertise",
        cand_profile,
        pref_title="Principal Architect",
        pref_company="Acme Corp",
        url="https://example.com/job/123",
        extra_param="custom_value"
    )
    assert isinstance(result, dict)
    assert result.get("company") in ("Acme Corp", "Target Company")
    assert "Principal Architect" in (result.get("title") or "") or "Target Role" in (result.get("title") or "")
    assert "match_score" in result

def test_finding_8_ssrf_url_validation():
    # Loopback & Localhost
    assert not is_safe_job_url("http://127.0.0.1:8000/api")
    assert not is_safe_job_url("http://localhost:8080")
    assert not is_safe_job_url("http://127.0.0.1")
    
    # Cloud metadata (AWS/GCP/Azure)
    assert not is_safe_job_url("http://169.254.169.254/latest/meta-data/")
    
    # Private RFC 1918 subnets
    assert not is_safe_job_url("http://10.0.0.1/status")
    assert not is_safe_job_url("http://192.168.1.1/admin")
    assert not is_safe_job_url("http://172.16.0.1:8080")
    
    # Internal docker name
    assert not is_safe_job_url("http://host.docker.internal:8000")
    
    # Dangerous schemes
    assert not is_safe_job_url("file:///etc/passwd")
    assert not is_safe_job_url("ftp://example.com")
    assert not is_safe_job_url("")

def test_finding_18_cv_html_autoescape():
    profile = {
        "full_name": "Test User",
        "tagline": "Architect",
        "skills": {},
        "experience": [{
            "company": "SecureCorp",
            "role": "Lead",
            "dates": "2020 - 2024",
            "bullets": [
                {"id": "b1", "text": '<iframe src="file:///etc/passwd"></iframe><script>alert(1)</script>', "default": True}
            ]
        }]
    }
    rendered_html = render_cv_html(profile)
    # Check that tags are escaped and raw executable tags are neutralized
    assert '<iframe src="file:///etc/passwd">' not in rendered_html
    assert '<script>alert(1)</script>' not in rendered_html
    assert '&lt;iframe' in rendered_html or '&lt;script&gt;' in rendered_html

def test_finding_19_backup_microsecond_resolution():
    fn1 = backup_profile_to_file()
    fn2 = backup_profile_to_file()
    assert fn1 is not None
    assert fn2 is not None
    # Microsecond timestamps prevent collisions even when executed immediately
    assert fn1 != fn2
    backups_dir = Path(settings.DATA_DIR) / "backups"
    assert (backups_dir / fn1).exists()
    assert (backups_dir / fn2).exists()

def test_finding_21_cors_restriction(client):
    # Test that untrusted origin does NOT receive Access-Control-Allow-Origin reflecting attacker domain
    response = client.options("/api/v1/profile", headers={
        "Origin": "https://malicious-attacker.com",
        "Access-Control-Request-Method": "GET"
    })
    allow_origin = response.headers.get("access-control-allow-origin")
    assert allow_origin != "https://malicious-attacker.com"
    assert allow_origin != "*"

def test_finding_22_database_context_manager():
    # Context manager properly closes connection
    with get_db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1
    # After exiting block, connection should be closed
    with pytest.raises(Exception):
        conn.execute("SELECT 1")

    # Compatibility shim import
    import app.database as legacy_db
    assert hasattr(legacy_db, "get_db")
    assert hasattr(legacy_db, "get_db_session")

def test_finding_42_tailored_inputs_and_master_path():
    master_path = get_master_cv_path()
    assert str(settings.DATA_DIR) in str(master_path)
    assert master_path.name == "master_cv.pdf"

def test_finding_43_profile_upload_size_and_doc_rejection(client):
    # Reject legacy .doc file
    response = client.post(
        "/api/v1/profile/upload",
        files={"file": ("resume.doc", b"fake binary doc content", "application/msword")}
    )
    assert response.status_code == 400
    assert "Legacy .doc format is not supported" in response.json()["detail"]

    # Reject empty file
    response_empty = client.post(
        "/api/v1/profile/upload",
        files={"file": ("empty.txt", b"", "text/plain")}
    )
    assert response_empty.status_code == 400

    # Test extract_text_from_file_bytes doc ValueError
    with pytest.raises(ValueError) as excinfo:
        extract_text_from_file_bytes("resume.doc", b"content")
    assert "Legacy .doc format is not supported" in str(excinfo.value)

    # ScanStartRequest accepts tax_free_only
    req = ScanStartRequest(location="Israel", tax_free_only=True)
    assert req.tax_free_only is True

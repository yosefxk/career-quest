import pytest
from app.engines.cv_renderer import render_cv_html, generate_cv_markdown, filter_experience_bullets
from app.engines.job_analyzer import audit_ats_compliance

@pytest.fixture
def sample_profile():
    return {
        "full_name": "Jordan Rivera",
        "email": "jordan.rivera@example.com",
        "phone": "+1 555-0199",
        "location": "Seattle, WA",
        "citizenship": "US Citizen",
        "tagline": "Senior Backend & Distributed Systems Engineer",
        "skills": {
            "Core Technologies": ["Go", "Python", "Kubernetes", "gRPC", "PostgreSQL"],
            "Cloud & Infra": ["AWS", "Docker", "Terraform", "CI/CD"]
        },
        "experience": [
            {
                "company": "CloudScale Inc.",
                "role": "Staff Software Engineer",
                "dates": "2021 – Present",
                "bullets": [
                    {"id": "b1", "text": "Architected low-latency microservices in Go handling 40k req/sec with Kubernetes.", "default": True},
                    {"id": "b2", "text": "Reduced cloud compute costs by 35% on AWS through container bin-packing and spot instances.", "default": True},
                    {"id": "b3", "text": "Led migration from monolithic architecture to gRPC microservices across 5 squads.", "default": True},
                    {"id": "b4", "text": "Established CI/CD deployment pipelines cutting lead time from 2 weeks to 15 minutes.", "default": True}
                ]
            },
            {
                "company": "TechCore Systems",
                "role": "Senior Backend Developer",
                "dates": "2018 – 2021",
                "bullets": [
                    {"id": "b5", "text": "Engineered REST APIs and asynchronous event processing with PostgreSQL and Redis.", "default": True},
                    {"id": "b6", "text": "Automated integration testing suite raising test coverage to 92%.", "default": True},
                    {"id": "b7", "text": "Optimized database queries decreasing p99 latency by 60%.", "default": False}
                ]
            }
        ],
        "education": [
            {
                "institution": "University of Washington",
                "degree": "B.Sc. in Computer Science",
                "dates": "2017 – 2021",
                "honors": "Magna Cum Laude"
            }
        ]
    }

def test_bullet_filtering(sample_profile):
    exp = sample_profile["experience"]
    
    # Test default bullet selection
    default_filtered = filter_experience_bullets(exp, selected_bullet_ids=None)
    assert len(default_filtered[0]["active_bullets"]) == 4

    # Test explicit bullet selection
    explicit_filtered = filter_experience_bullets(exp, selected_bullet_ids=["b7"])
    assert len(explicit_filtered) == 1
    assert explicit_filtered[0]["active_bullets"][0]["id"] == "b7"

def test_html_and_markdown_generation(sample_profile):
    html = render_cv_html(sample_profile, custom_summary="Custom tailored headline.")
    assert "Jordan Rivera" in html
    assert "Custom tailored headline." in html
    assert "CloudScale Inc." in html

    md = generate_cv_markdown(sample_profile, custom_summary="Custom tailored headline.")
    assert "# Jordan Rivera" in md
    assert "## Executive Summary" in md
    assert "Architected low-latency microservices" in md

def test_ats_compliance_auditor(sample_profile):
    html = render_cv_html(sample_profile, custom_summary="Senior software engineer with deep cloud scale.")
    audit = audit_ats_compliance(html, sample_profile, job_description="Looking for a Kubernetes and Go engineer.")
    
    assert "ats_score" in audit
    assert audit["ats_score"] >= 80
    assert audit["status"] in ["PASS", "WARNING"]
    assert len(audit["checks"]) >= 4

def test_llm_gateway_multi_provider(monkeypatch):
    from app.core.llm_gateway import LLMGateway
    
    # 1. Test Local Ollama Provider (no API key required)
    gw_ollama = LLMGateway()
    gw_ollama.provider = "ollama"
    gw_ollama.api_key = ""
    gw_ollama.model = "llama3.1"
    
    assert gw_ollama._is_local_provider() is True
    
    # Mock httpx call for ollama generate
    class FakeResponse:
        status_code = 200
        def json(self):
            return {"response": '{"summary": "Local Ollama Test"}'}
            
    import httpx
    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kwargs: FakeResponse())
    
    res = gw_ollama.generate_json("Test prompt")
    assert res == {"summary": "Local Ollama Test"}

    # 2. Test Local OpenAI-compatible Provider (LM Studio / vLLM)
    gw_local = LLMGateway()
    gw_local.provider = "local"
    gw_local.api_key = ""
    gw_local.model = "qwen2.5-coder-7b"
    assert gw_local._is_local_provider() is True
    assert "1234" in gw_local._get_openai_compatible_base_url()

    class FakeOpenAIResponse:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": '{"level": "Senior"}'}}]}

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kwargs: FakeOpenAIResponse())
    res_local = gw_local.generate_json("Test local")
    assert res_local == {"level": "Senior"}


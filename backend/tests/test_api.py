import pytest

def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "CareerQuest"

def test_system_status(client):
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert "ai_provider" in data
    assert "ai_model" in data

def test_get_and_update_profile(client):
    # Get initial profile
    get_res = client.get("/api/v1/profile")
    assert get_res.status_code == 200
    prof = get_res.json()
    assert "full_name" in prof
    assert "email" in prof

    # Update profile
    update_res = client.put("/api/v1/profile", json={
        "full_name": "Taylor Morgan",
        "tagline": "Staff Cloud Architect & Systems Lead",
        "location": "San Francisco, CA"
    })
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["full_name"] == "Taylor Morgan"
    assert updated["location"] == "San Francisco, CA"

def test_job_lifecycle(client):
    # 1. Create a job
    create_res = client.post("/api/v1/jobs", json={
        "company": "Scale Dynamics",
        "title": "Principal Solutions Architect",
        "location": "Remote",
        "salary": "$210k - $260k",
        "status": "wishlist",
        "match_score": 94,
        "job_description": "We are seeking a Principal Solutions Architect to scale cloud infrastructure."
    })
    assert create_res.status_code == 200
    job_id = create_res.json()["id"]

    # 2. Get jobs
    jobs_res = client.get("/api/v1/jobs")
    assert jobs_res.status_code == 200
    jobs = jobs_res.json()
    found = [j for j in jobs if j["id"] == job_id]
    assert len(found) == 1
    assert found[0]["company"] == "Scale Dynamics"

    # 3. Update job stage
    patch_res = client.patch(f"/api/v1/jobs/{job_id}", json={
        "status": "tailoring",
        "custom_summary": "Tailored executive summary highlighting cloud scale."
    })
    assert patch_res.status_code == 200

    # 4. Freeze snapshot
    snap_res = client.post(f"/api/v1/jobs/{job_id}/snapshot", json={
        "stage": "applied",
        "custom_summary": "Final submitted resume summary.",
        "selected_bullets": ["b1", "b2"]
    })
    assert snap_res.status_code == 200

    # 5. Verify snapshot history
    hist_res = client.get(f"/api/v1/jobs/{job_id}/snapshots")
    assert hist_res.status_code == 200
    snaps = hist_res.json()
    assert len(snaps) >= 1
    assert snaps[0]["stage"] == "applied"

def test_digest_filtering(client):
    res = client.get("/api/v1/digest?region=all&category=all")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

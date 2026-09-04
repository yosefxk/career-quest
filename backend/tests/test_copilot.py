import pytest
from app.engines.job_analyzer import get_directives_block

def test_directives_lifecycle(client):
    # 1. Get initial seeded directives
    get_res = client.get("/api/v1/copilot/directives")
    assert get_res.status_code == 200
    directives = get_res.json()
    assert len(directives) >= 1
    assert any(d["category"] in ["cv_style", "formatting", "tone"] for d in directives)

    # 2. Create new custom directive
    create_res = client.post("/api/v1/copilot/directives", json={
        "rule_text": "Always emphasize latency reduction and cost efficiency in cloud infrastructure bullets.",
        "category": "cv_style"
    })
    assert create_res.status_code == 200
    created = create_res.json()
    directive_id = created["id"]
    assert created["rule_text"].startswith("Always emphasize latency reduction")
    assert created["is_active"] is True
    assert created["source"] == "manual"

    # 3. Patch directive (toggle inactive)
    patch_res = client.patch(f"/api/v1/copilot/directives/{directive_id}", json={
        "is_active": False
    })
    assert patch_res.status_code == 200
    assert patch_res.json()["is_active"] is False

    # 4. Delete directive
    del_res = client.delete(f"/api/v1/copilot/directives/{directive_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

def test_copilot_chat_and_history(client):
    # 1. Send chat message
    chat_res = client.post("/api/v1/copilot/chat", json={
        "message": "What are the most effective ways to showcase distributed systems scale on my resume?",
        "focused_job_id": None
    })
    assert chat_res.status_code == 200
    data = chat_res.json()
    assert "reply" in data
    assert len(data["reply"]) > 10

    # 2. Verify messages exist in history
    hist_res = client.get("/api/v1/copilot/messages")
    assert hist_res.status_code == 200
    messages = hist_res.json()
    assert len(messages) >= 2  # user message + assistant reply
    assert messages[-2]["role"] == "user"
    assert messages[-1]["role"] == "assistant"

    # 3. Clear messages
    clear_res = client.delete("/api/v1/copilot/messages")
    assert clear_res.status_code == 200
    assert clear_res.json()["status"] == "cleared"

    # 4. Verify history is empty
    empty_res = client.get("/api/v1/copilot/messages")
    assert empty_res.status_code == 200
    assert len(empty_res.json()) == 0

def test_directives_block_injection():
    sample_directives = [
        {"category": "cv_style", "rule_text": "Quantify outcomes in USD."},
        {"category": "tone", "rule_text": "Avoid buzzwords."}
    ]
    block = get_directives_block(sample_directives)
    assert "STRICT USER DIRECTIVES" in block
    assert "Quantify outcomes in USD." in block
    assert "Avoid buzzwords." in block

def test_copilot_operational_actions(client):
    # 1. Create a test job
    job_res = client.post("/api/v1/jobs", json={
        "company": "Stripe",
        "title": "Staff Infrastructure Engineer",
        "status": "wishlist"
    })
    assert job_res.status_code == 200
    job_id = job_res.json()["id"]

    # 2. Command the Coach to update status
    chat_res = client.post("/api/v1/copilot/chat", json={
        "message": f"Mark job #{job_id} as applied",
        "focused_job_id": job_id
    })
    assert chat_res.status_code == 200
    data = chat_res.json()
    assert data.get("action_executed") is not None
    assert data["action_executed"]["type"] == "job_updated"
    assert data["action_executed"]["job_id"] == job_id

    # 3. Verify in database
    get_job = client.get(f"/api/v1/jobs")
    matched = [j for j in get_job.json() if j["id"] == job_id]
    assert len(matched) == 1
    assert matched[0]["status"] == "applied"

    # 4. Command the Coach to add a note
    note_res = client.post("/api/v1/copilot/chat", json={
        "message": f"Add note to Stripe: Recruiter replied, screening call next Tuesday",
        "focused_job_id": job_id
    })
    assert note_res.status_code == 200
    note_data = note_res.json()
    assert note_data.get("action_executed") is not None
    assert note_data["action_executed"]["type"] == "job_updated"


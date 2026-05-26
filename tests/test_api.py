"""API integration tests via FastAPI TestClient against the in-memory DB."""


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_classify_success_and_404(client, seeded):
    ok = client.post("/api/v1/classify", json={"email_id": seeded["faq_email"].email_id})
    assert ok.status_code == 200
    assert "intent" in ok.json()
    assert client.post("/api/v1/classify", json={"email_id": "nope"}).status_code == 404


def test_context_success_and_404(client, seeded):
    ok = client.get(f"/api/v1/customers/{seeded['free'].customer_id}/context")
    assert ok.status_code == 200
    assert ok.json()["customer"]["name"] == "Free Fred"
    assert client.get("/api/v1/customers/nope/context").status_code == 404


def test_draft_then_queue_then_action(client, seeded):
    # Create a draft for the FAQ email.
    res = client.post(
        "/api/v1/draft",
        json={"email_id": seeded["faq_email"].email_id, "intent": "General FAQ", "confidence": 0.9},
    )
    assert res.status_code == 200
    draft_id = res.json()["draft_id"]

    # It shows up in the pending queue.
    queue = client.get("/api/v1/drafts", params={"status": "pending"}).json()
    assert any(it["draft_id"] == draft_id for it in queue["items"])

    # Detail loads the 3-panel payload.
    detail = client.get(f"/api/v1/drafts/{draft_id}").json()
    assert detail["email"]["subject"] == "What are your hours?"
    assert "recent_orders" in detail["context"]

    # Edit & approve flips status to sent and records an audit event.
    act = client.patch(
        f"/api/v1/drafts/{draft_id}/action",
        json={"action": "edit", "edited_body": "Edited reply."},
    )
    assert act.status_code == 200
    assert act.json()["status"] == "sent"


def test_action_validation_errors(client, seeded):
    res = client.post(
        "/api/v1/draft",
        json={
            "email_id": seeded["refund_email"].email_id,
            "intent": "Refund Request",
            "confidence": 0.5,
        },
    )
    draft_id = res.json()["draft_id"]
    # Reject without a reason is rejected by validation.
    bad = client.patch(f"/api/v1/drafts/{draft_id}/action", json={"action": "reject"})
    assert bad.status_code == 422
    # Unknown action is rejected.
    assert (
        client.patch(f"/api/v1/drafts/{draft_id}/action", json={"action": "frobnicate"}).status_code
        == 422
    )


def test_metrics_endpoint(client, seeded):
    res = client.get("/api/v1/metrics")
    assert res.status_code == 200
    body = res.json()
    assert "zero_touch_rate" in body
    assert body["total_emails"] == 2

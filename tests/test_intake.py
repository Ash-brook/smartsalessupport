"""Integration tests for the /intake endpoint (drag-and-drop mail feed)."""

from email.message import EmailMessage


def _eml(sender: str, subject: str, body: str) -> bytes:
    m = EmailMessage()
    m["From"] = sender
    m["Subject"] = subject
    m.set_content(body)
    return m.as_bytes()


def test_intake_eml_creates_reviewable_draft(client):
    data = _eml("Jane Doe <jane@x.com>", "Refund please", "I want a refund — this is unacceptable.")
    res = client.post("/api/v1/intake", files={"files": ("c.eml", data, "message/rfc822")})
    assert res.status_code == 200
    item = res.json()["results"][0]
    assert item["ok"] is True
    assert item["source"] == "eml"
    assert item["customer_name"] == "Jane Doe"
    assert item["draft_id"]

    # The new complaint shows up in the agent review queue.
    queue = client.get("/api/v1/drafts", params={"status": "pending", "page_size": 100}).json()
    assert any(it["draft_id"] == item["draft_id"] for it in queue["items"])


def test_intake_unknown_sender_creates_customer(client):
    data = _eml("new@nowhere.com", "Question", "Do you ship to Canada?")
    res = client.post("/api/v1/intake", files={"files": ("q.eml", data, "message/rfc822")})
    item = res.json()["results"][0]
    assert item["ok"] is True
    assert item["customer_name"]  # a customer was matched or created


def test_intake_empty_file_reports_error(client):
    res = client.post("/api/v1/intake", files={"files": ("empty.txt", b"", "text/plain")})
    item = res.json()["results"][0]
    assert item["ok"] is False
    assert item["error"]

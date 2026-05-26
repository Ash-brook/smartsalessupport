"""Unit tests for the file-ingest service (the mail intake parsers)."""

from email.message import EmailMessage

from backend.services.ingest import ingest_file
from backend.services.llm_client import LLMClient


def _eml_bytes(sender: str, subject: str, body: str) -> bytes:
    m = EmailMessage()
    m["From"] = sender
    m["Subject"] = subject
    m.set_content(body)
    return m.as_bytes()


def test_eml_extraction():
    data = _eml_bytes("Bob Jones <bob@acme.com>", "App crash", "The app keeps crashing on login.")
    out = ingest_file("c.eml", data, "message/rfc822", LLMClient())
    assert out.source == "eml"
    assert out.sender_email == "bob@acme.com"
    assert out.sender_name == "Bob Jones"
    assert out.subject == "App crash"
    assert "crashing" in out.body


def test_plain_text_fallback():
    out = ingest_file(
        "note.txt", b"Just a plain complaint about billing.", "text/plain", LLMClient()
    )
    assert out.source == "text"
    assert "billing" in out.body


def test_image_routes_to_vision():
    # In mock mode the vision call returns a placeholder; we only check routing + non-empty body.
    out = ingest_file("shot.png", b"\x89PNG not-a-real-image", "image/png", LLMClient())
    assert out.source == "vision"
    assert out.body  # non-empty so the pipeline has something to classify

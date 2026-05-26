"""Read an incoming complaint file into a structured form (the 'mail intake' feed).

Supports the formats a real support inbox receives:
  - .eml  (standard email export, e.g. Gmail "Show original")  -> parsed locally
  - .msg  (Outlook)                                            -> parsed locally
  - .pdf  (text PDFs parsed locally; scanned PDFs via vision)
  - images (.png/.jpg/...)                                     -> Gemini vision

Returns an ExtractedComplaint; the intake endpoint turns it into an inbox email.
"""

import io
import os
import re
import tempfile
from dataclasses import dataclass
from email import message_from_bytes
from email.utils import parseaddr

from backend.services.llm_client import LLMClient

# If a PDF yields less text than this, we treat it as scanned and send it to vision.
_MIN_PDF_TEXT = 20
_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}


@dataclass
class ExtractedComplaint:
    sender_email: str | None
    sender_name: str | None
    subject: str
    body: str
    source: str  # how it was read: eml | msg | pdf | vision | text


def ingest_file(
    filename: str, content: bytes, mime_type: str | None, client: LLMClient
) -> ExtractedComplaint:
    """Dispatch on file type and extract the complaint."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    mime = (mime_type or "").lower()

    if ext == "eml" or mime == "message/rfc822":
        return _from_eml(content)
    if ext == "msg":
        return _from_msg(content)
    if ext == "pdf" or mime == "application/pdf":
        return _from_pdf(content, client)
    if ext in _IMAGE_EXTS or mime.startswith("image/"):
        return _from_vision(content, mime or "image/png", client, source="vision")

    # Fallback: treat the bytes as plain text.
    text = content.decode("utf-8", "ignore").strip()
    return ExtractedComplaint(None, None, _first_line(text), text, "text")


def _first_line(text: str, default: str = "Customer complaint") -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:120]
    return default


def _email_body(msg) -> str:
    """Pull the best-effort plain-text body out of a parsed email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", "ignore").strip()
        # No plain part — fall back to stripping the first HTML part.
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True) or b""
                html = payload.decode(part.get_content_charset() or "utf-8", "ignore")
                return re.sub(r"<[^>]+>", "", html).strip()
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", "ignore").strip()


def _from_eml(content: bytes) -> ExtractedComplaint:
    msg = message_from_bytes(content)
    name, addr = parseaddr(msg.get("From", ""))
    return ExtractedComplaint(
        sender_email=addr or None,
        sender_name=name or None,
        subject=(msg.get("Subject") or "Customer complaint").strip(),
        body=_email_body(msg),
        source="eml",
    )


def _from_msg(content: bytes) -> ExtractedComplaint:
    import extract_msg

    # extract_msg reads from a path, so spool the bytes to a temp file.
    tmp = tempfile.NamedTemporaryFile(suffix=".msg", delete=False)
    try:
        tmp.write(content)
        tmp.close()
        msg = extract_msg.Message(tmp.name)
        name, addr = parseaddr(msg.sender or "")
        return ExtractedComplaint(
            sender_email=addr or None,
            sender_name=name or (msg.sender or None),
            subject=(msg.subject or "Customer complaint").strip(),
            body=(msg.body or "").strip(),
            source="msg",
        )
    finally:
        os.unlink(tmp.name)


def _from_pdf(content: bytes, client: LLMClient) -> ExtractedComplaint:
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(content))
    text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if len(text) < _MIN_PDF_TEXT:
        # Likely a scanned PDF with no embedded text — let vision read it.
        return _from_vision(content, "application/pdf", client, source="vision")
    return ExtractedComplaint(None, None, _first_line(text), text, "pdf")


def _from_vision(
    content: bytes, mime_type: str, client: LLMClient, source: str
) -> ExtractedComplaint:
    result = client.extract_complaint(content, mime_type)
    return ExtractedComplaint(
        sender_email=result.get("sender_email") or None,
        sender_name=None,
        subject=result.get("subject") or "Customer complaint",
        body=result.get("body") or "",
        source=source,
    )

"""Draft generation service.

Calls the LLM to write a reply, then persists it as a Draft row (status = pending) carrying
the classification result so the review UI has everything in one place. Returns the Draft and
the model metadata (model_used, latency_ms) the API contract needs.
"""

from typing import Any

from sqlalchemy.orm import Session

from backend.models import Draft, DraftStatus, IntentLabel, SimulatedEmail
from backend.services.hallucination import detect
from backend.services.llm_client import LLMClient


def create_draft(
    session: Session,
    client: LLMClient,
    email: SimulatedEmail,
    *,
    intent: str,
    confidence: float,
    reasoning: str | None,
    context: dict[str, Any],
) -> tuple[Draft, dict[str, Any]]:
    """Generate and store a draft reply for `email`. Returns (draft_row, llm_metadata)."""
    result = client.draft(intent, context, email.body_text)

    # Safety net: flag any concrete fact in the draft that isn't grounded in the context,
    # and force human review if we find one (PRD task #14 / risk #2).
    flags = list(result["flags"])
    requires_review = result["requires_human_review"]
    hallucinations = detect(result["body"], context)
    if hallucinations:
        flags.extend(hallucinations)
        requires_review = True

    draft = Draft(
        email_id=email.email_id,
        intent=IntentLabel(intent) if intent in {i.value for i in IntentLabel} else None,
        confidence=confidence,
        reasoning=reasoning,
        subject=result["subject"],
        body=result["body"],
        requires_human_review=requires_review,
        flags=flags,
        model_used=result["model_used"],
        status=DraftStatus.PENDING,
    )
    session.add(draft)
    session.flush()  # assign draft_id

    metadata = {"model_used": result["model_used"], "latency_ms": result["latency_ms"]}
    return draft, metadata

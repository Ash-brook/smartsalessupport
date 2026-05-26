"""Core per-email pipeline logic (PRD section 6.2), as a testable service.

`process_one` runs a single email through every stage against a given session. The async
runner (scripts/run_pipeline.py) wraps this with polling, throttling, and a write lock;
tests call it directly. Keeping the logic here (not in the script) means the runner and the
tests exercise exactly the same code.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.models import (
    AuditAction,
    AuditEvent,
    DraftStatus,
    EmailStatus,
    SimulatedEmail,
)
from backend.services.draft import create_draft
from backend.services.enrich import build_context
from backend.services.llm_client import LLMClient
from backend.services.routing import evaluate

# Below this confidence we skip the context lookup; the email goes to a human anyway.
ENRICH_CONFIDENCE_FLOOR = 0.7


@dataclass
class PipelineResult:
    outcome: str  # "auto" or "hitl"
    intent: str
    confidence: float
    reasons: list[str]  # why it was routed to HITL (empty if auto)


def process_one(session: Session, client: LLMClient, email_id: str) -> PipelineResult:
    """Run one email through classify -> enrich -> draft -> route -> audit. Commits the session."""
    email = session.get(SimulatedEmail, email_id)
    email.status = EmailStatus.PROCESSING

    classification = client.classify(email.body_text)
    intent = classification["intent"]
    confidence = classification["confidence"]

    context = {}
    if confidence >= ENRICH_CONFIDENCE_FLOOR:
        context = build_context(session, email.customer_id) or {}

    draft, _ = create_draft(
        session,
        client,
        email,
        intent=intent,
        confidence=confidence,
        reasoning=classification["reasoning"],
        context=context,
    )

    tier = (context.get("customer") or {}).get("account_tier", "")
    decision = evaluate(
        intent=intent,
        confidence=confidence,
        requires_human_review=draft.requires_human_review,
        flags=draft.flags,
        account_tier=tier,
    )

    if decision.auto_approve:
        email.status = EmailStatus.SENT
        draft.status = DraftStatus.SENT
        action = AuditAction.AUTO_APPROVED
        outcome = "auto"
    else:
        email.status = EmailStatus.DRAFTED  # waits in the HITL queue
        draft.status = DraftStatus.PENDING
        action = AuditAction.DRAFTED
        outcome = "hitl"

    session.add(
        AuditEvent(
            email_id=email.email_id,
            draft_id=draft.draft_id,
            action=action,
            agent_id="pipeline",
        )
    )
    session.commit()
    return PipelineResult(
        outcome=outcome, intent=intent, confidence=confidence, reasons=decision.reasons
    )

"""Pipeline integration tests — the full classify -> draft -> route -> audit flow,
exercised through backend.services.pipeline.process_one against the test DB."""

from datetime import datetime

from backend.models import (
    AuditEvent,
    Draft,
    EmailStatus,
    IntentLabel,
    SimulatedEmail,
)
from backend.services.llm_client import LLMClient
from backend.services.pipeline import process_one


def _add_email(session, customer_id, body, intent):
    email = SimulatedEmail(
        customer_id=customer_id,
        subject="Test",
        body_text=body,
        received_at=datetime(2025, 4, 1),
        intent_label=intent,
    )
    session.add(email)
    session.commit()
    return email


def test_enterprise_refund_routes_to_hitl(session, seeded):
    result = process_one(session, LLMClient(), seeded["refund_email"].email_id)
    assert result.outcome == "hitl"
    assert result.reasons  # at least one trigger fired

    email = session.get(SimulatedEmail, seeded["refund_email"].email_id)
    assert email.status == EmailStatus.DRAFTED
    assert session.query(Draft).filter_by(email_id=email.email_id).count() == 1
    assert session.query(AuditEvent).filter_by(email_id=email.email_id).count() == 1


def test_clear_order_status_auto_approves(session, seeded):
    # A confident, auto-eligible, Free-tier email with no risky keywords -> auto.
    email = _add_email(
        session,
        seeded["free"].customer_id,
        "Where is my order? The delivery tracking shows it shipped but it has not arrived.",
        IntentLabel.ORDER_STATUS,
    )
    result = process_one(session, LLMClient(), email.email_id)
    assert result.outcome == "auto"
    assert result.reasons == []
    assert session.get(SimulatedEmail, email.email_id).status == EmailStatus.SENT

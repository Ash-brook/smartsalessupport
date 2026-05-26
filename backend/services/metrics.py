"""Manager dashboard metrics (PRD section 10).

Aggregates the KPIs from the emails, drafts, and audit_events tables in one pass-ish query.
All rates are returned as fractions (0.0-1.0); the frontend formats them as percentages.
"""

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (
    AuditAction,
    AuditEvent,
    Customer,
    Draft,
    EmailStatus,
    SimulatedEmail,
)


def compute_metrics(session: Session) -> dict:
    # Audit-event counts capture pipeline + agent outcomes.
    action_counts = Counter(
        dict(
            session.execute(
                select(AuditEvent.action, func.count()).group_by(AuditEvent.action)
            ).all()
        )
    )
    auto = action_counts.get(AuditAction.AUTO_APPROVED, 0)
    drafted = action_counts.get(AuditAction.DRAFTED, 0)  # routed to HITL by the pipeline
    approved = action_counts.get(AuditAction.APPROVED, 0)
    edited = action_counts.get(AuditAction.EDITED_AND_APPROVED, 0)
    rejected_actions = action_counts.get(AuditAction.REJECTED, 0)

    processed = auto + drafted
    agent_decisions = approved + edited + rejected_actions

    # Email status snapshot.
    status_counts = Counter(
        dict(
            session.execute(
                select(SimulatedEmail.status, func.count()).group_by(SimulatedEmail.status)
            ).all()
        )
    )
    total_emails = session.scalar(select(func.count()).select_from(SimulatedEmail)) or 0

    # Category breakdown by predicted intent.
    category_rows = session.execute(select(Draft.intent, func.count()).group_by(Draft.intent)).all()
    category_breakdown = [
        {"intent": intent.value if intent else "Unknown", "count": n}
        for intent, n in sorted(category_rows, key=lambda r: r[1], reverse=True)
    ]

    # Recent audit log with the email subject + customer name.
    log_rows = session.execute(
        select(AuditEvent, SimulatedEmail, Customer)
        .join(SimulatedEmail, AuditEvent.email_id == SimulatedEmail.email_id)
        .join(Customer, SimulatedEmail.customer_id == Customer.customer_id)
        .order_by(AuditEvent.timestamp.desc())
        .limit(15)
    ).all()
    audit_log = [
        {
            "timestamp": a.timestamp,
            "action": a.action.value,
            "agent_id": a.agent_id,
            "customer_name": c.name,
            "subject": e.subject,
        }
        for a, e, c in log_rows
    ]

    # Top rejection reasons.
    reason_rows = session.execute(
        select(AuditEvent.rejection_reason, func.count())
        .where(AuditEvent.action == AuditAction.REJECTED)
        .where(AuditEvent.rejection_reason.is_not(None))
        .group_by(AuditEvent.rejection_reason)
        .order_by(func.count().desc())
        .limit(5)
    ).all()
    top_rejection_reasons = [{"reason": r, "count": n} for r, n in reason_rows]

    def rate(num: int, denom: int) -> float:
        return round(num / denom, 4) if denom else 0.0

    return {
        "total_emails": total_emails,
        "processed": processed,
        "auto_approved": auto,
        "hitl": drafted,
        "pending": status_counts.get(EmailStatus.DRAFTED, 0),
        "sent": status_counts.get(EmailStatus.SENT, 0),
        "rejected": status_counts.get(EmailStatus.REJECTED, 0),
        "zero_touch_rate": rate(auto, processed),
        "hitl_rate": rate(drafted, processed),
        "edit_rate": rate(edited, approved + edited),
        "rejection_rate": rate(rejected_actions, agent_decisions),
        "category_breakdown": category_breakdown,
        "audit_log": audit_log,
        "top_rejection_reasons": top_rejection_reasons,
    }

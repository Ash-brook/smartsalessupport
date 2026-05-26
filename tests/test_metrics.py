"""Metrics aggregation tests (PRD section 10)."""

from backend.services.llm_client import LLMClient
from backend.services.metrics import compute_metrics
from backend.services.pipeline import process_one


def test_metrics_after_processing(session, seeded):
    # Process both seeded emails so there are audit events to aggregate.
    process_one(session, LLMClient(), seeded["faq_email"].email_id)
    process_one(session, LLMClient(), seeded["refund_email"].email_id)

    m = compute_metrics(session)
    assert m["total_emails"] == 2
    assert m["processed"] == 2
    assert m["auto_approved"] + m["hitl"] == 2
    # Rates are fractions in 0..1.
    for key in ("zero_touch_rate", "hitl_rate", "edit_rate", "rejection_rate"):
        assert 0.0 <= m[key] <= 1.0
    assert isinstance(m["category_breakdown"], list)
    assert isinstance(m["audit_log"], list)

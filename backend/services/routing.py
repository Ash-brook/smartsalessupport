"""Routing engine — decides auto-reply vs. human review (PRD section 7.2).

An email is sent to the Agent Review queue (HITL) if ANY trigger fires. Only emails that
clear every trigger are auto-approved. Each decision carries human-readable reasons so the
audit trail and dashboard can explain *why* something needed a human.
"""

from dataclasses import dataclass

from backend.models import AUTO_REPLY_ELIGIBLE, AccountTier, IntentLabel

CONFIDENCE_THRESHOLD = 0.85


@dataclass
class RoutingDecision:
    auto_approve: bool
    reasons: list[str]  # why it was routed to HITL (empty if auto-approved)


def evaluate(
    *,
    intent: str,
    confidence: float,
    requires_human_review: bool,
    flags: list[str],
    account_tier: str,
) -> RoutingDecision:
    reasons: list[str] = []

    # Some intents always need human judgement (Technical Support, Refund Request).
    if intent not in {i.value for i in AUTO_REPLY_ELIGIBLE}:
        reasons.append(f"intent '{intent}' always requires human review")

    if confidence < CONFIDENCE_THRESHOLD:
        reasons.append(f"low confidence ({confidence:.2f} < {CONFIDENCE_THRESHOLD})")

    if requires_human_review:
        reasons.append("model flagged its own draft for review")

    if flags:
        reasons.append(f"draft flags: {', '.join(flags)}")

    # Every Enterprise customer email gets a human look, regardless of intent.
    if account_tier == AccountTier.ENTERPRISE.value:
        reasons.append("Enterprise customer")

    return RoutingDecision(auto_approve=not reasons, reasons=reasons)


def is_known_intent(intent: str | None) -> bool:
    """True if the classifier returned one of our known categories."""
    return intent in {i.value for i in IntentLabel}

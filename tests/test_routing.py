"""Routing engine unit tests (PRD 7.2). Each HITL trigger must force human review,
and a clean auto-eligible case must auto-approve."""

from backend.services.routing import CONFIDENCE_THRESHOLD, evaluate


def _eval(**overrides):
    base = dict(
        intent="Order Status",
        confidence=0.95,
        requires_human_review=False,
        flags=[],
        account_tier="Free",
    )
    base.update(overrides)
    return evaluate(**base)


def test_clean_auto_eligible_is_auto_approved():
    assert _eval().auto_approve is True


def test_non_eligible_intent_goes_to_hitl():
    assert _eval(intent="Refund Request").auto_approve is False
    assert _eval(intent="Technical Support").auto_approve is False


def test_low_confidence_goes_to_hitl():
    assert _eval(confidence=CONFIDENCE_THRESHOLD - 0.01).auto_approve is False


def test_model_self_flag_goes_to_hitl():
    assert _eval(requires_human_review=True).auto_approve is False


def test_any_flag_goes_to_hitl():
    decision = _eval(flags=["high_refund_amount"])
    assert decision.auto_approve is False
    assert any("flags" in r for r in decision.reasons)


def test_enterprise_always_goes_to_hitl():
    assert _eval(account_tier="Enterprise").auto_approve is False


def test_reasons_listed_for_multiple_triggers():
    decision = _eval(intent="Refund Request", confidence=0.4, account_tier="Enterprise")
    assert len(decision.reasons) == 3

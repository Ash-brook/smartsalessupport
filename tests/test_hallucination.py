"""Hallucination guard unit tests (PRD task #14)."""

from backend.services.hallucination import detect

CONTEXT = {
    "customer": {"lifetime_value_usd": 120.0},
    "recent_orders": [
        {"order_id": "abcd1234ef", "amount_usd": 99.50, "tracking_number": "1ZABC123"},
    ],
}


def test_grounded_draft_has_no_flags():
    body = "Your order #ABCD1234 for $99.50 shipped via 1ZABC123."
    assert detect(body, CONTEXT) == []


def test_invented_amount_is_flagged():
    flags = detect("We refunded you $999.00.", CONTEXT)
    assert any(f.startswith("unverified_amount") for f in flags)


def test_invented_order_ref_is_flagged():
    flags = detect("Regarding order #ZZZ99999, ...", CONTEXT)
    assert any(f.startswith("unverified_order") for f in flags)


def test_invented_tracking_is_flagged():
    flags = detect("Tracking number 1ZFAKE999 is on its way.", CONTEXT)
    assert any(f.startswith("unverified_tracking") for f in flags)


def test_empty_context_flags_any_specifics():
    assert detect("Your order #ABCD1234 cost $99.50.", {}) != []

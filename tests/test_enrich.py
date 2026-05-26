"""Context enrichment unit tests (PRD 5.4)."""

from backend.services.enrich import build_context


def test_build_context_shape(session, seeded):
    ctx = build_context(session, seeded["free"].customer_id)
    assert ctx is not None
    assert ctx["customer"]["name"] == "Free Fred"
    assert ctx["customer"]["account_tier"] == "Free"
    assert len(ctx["recent_orders"]) == 1
    assert ctx["recent_orders"][0]["amount_usd"] == 99.50


def test_build_context_missing_customer_returns_none(session):
    assert build_context(session, "does-not-exist") is None

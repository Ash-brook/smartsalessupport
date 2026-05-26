"""LLMClient mock-mode unit tests. (MOCK_LLM defaults to true in the test environment.)"""

from backend.models import IntentLabel
from backend.services.llm_client import LLMClient

KNOWN_INTENTS = {i.value for i in IntentLabel}


def test_classify_returns_known_intent_and_metadata():
    res = LLMClient().classify("Where is my order? The delivery is late.")
    assert res["intent"] in KNOWN_INTENTS
    assert 0.0 <= res["confidence"] <= 1.0
    assert res["model_used"] == "mock"
    assert "latency_ms" in res


def test_classify_detects_refund_keyword():
    res = LLMClient().classify("I want a refund for my purchase.")
    assert res["intent"] == IntentLabel.REFUND_REQUEST.value


def test_draft_returns_expected_shape():
    ctx = {"customer": {"name": "Sam"}, "recent_orders": []}
    res = LLMClient().draft("Order Status", ctx, "Where is my order?")
    assert set(res) >= {"subject", "body", "requires_human_review", "flags", "model_used"}
    assert "Sam" in res["body"]


def test_draft_flags_high_value_refund():
    ctx = {"customer": {"name": "Sam"}, "recent_orders": [{"amount_usd": 350.0}]}
    res = LLMClient().draft("Refund Request", ctx, "I demand a refund, this is unacceptable.")
    assert res["requires_human_review"] is True
    assert "high_refund_amount" in res["flags"]

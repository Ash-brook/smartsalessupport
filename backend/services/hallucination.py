"""Hallucination post-processor (PRD task #14, risk #2).

The draft model is told to use only facts from the provided context, but LLMs sometimes
invent specifics (an order number, a price, a tracking code). This module scans a generated
draft for concrete facts and flags any that don't appear in the customer context. Anything
flagged forces the draft into human review — a cheap safety net behind the prompt itself.

Pure string/number logic, so it runs identically in mock and live mode.
"""

import re
from typing import Any

# Concrete facts we can verify against context.
_MONEY_RE = re.compile(r"\$\s?(\d+(?:\.\d{1,2})?)")
_ORDER_RE = re.compile(r"#([A-Za-z0-9]{6,})")
_TRACKING_RE = re.compile(r"\b(1Z[A-Z0-9]{6,})\b")


def _grounded_facts(context: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    """Collect the amounts, order refs, and tracking numbers present in the context."""
    amounts: set[str] = set()
    orders: set[str] = set()
    tracking: set[str] = set()

    for order in context.get("recent_orders", []):
        if (amt := order.get("amount_usd")) is not None:
            amounts.add(f"{float(amt):.2f}")
        if oid := order.get("order_id"):
            orders.add(oid[:8].upper())  # draft refs use the short "#XXXXXXXX" form
        if trk := order.get("tracking_number"):
            tracking.add(trk.upper())

    cust = context.get("customer") or {}
    if (ltv := cust.get("lifetime_value_usd")) is not None:
        amounts.add(f"{float(ltv):.2f}")

    return amounts, orders, tracking


def detect(draft_body: str, context: dict[str, Any]) -> list[str]:
    """Return a list of hallucination flags (empty if the draft is grounded)."""
    amounts, orders, tracking = _grounded_facts(context)
    flags: list[str] = []

    for raw in _MONEY_RE.findall(draft_body):
        if f"{float(raw):.2f}" not in amounts:
            flags.append(f"unverified_amount:${raw}")

    for ref in _ORDER_RE.findall(draft_body):
        if ref.upper() not in orders:
            flags.append(f"unverified_order:#{ref}")

    for trk in _TRACKING_RE.findall(draft_body):
        if trk.upper() not in tracking:
            flags.append(f"unverified_tracking:{trk}")

    return flags

"""Context enrichment — the simulated CRM lookup (PRD section 5.4).

Given a customer, returns the structured profile + recent orders + open tickets that the
draft stage and the review UI need. There's no real CRM; this reads our seeded SQLite data.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Customer, EmailStatus, Order, SimulatedEmail

# Statuses that count as an "open" support ticket for a customer.
_OPEN_STATUSES = (EmailStatus.UNPROCESSED, EmailStatus.PROCESSING, EmailStatus.DRAFTED)


def build_context(session: Session, customer_id: str) -> dict[str, Any] | None:
    """Return the context dict for a customer, or None if the customer doesn't exist.

    Shape matches ContextResponse: {customer, recent_orders (last 3), open_tickets (last 5)}.
    """
    customer = session.get(Customer, customer_id)
    if customer is None:
        return None

    recent_orders = session.scalars(
        select(Order)
        .where(Order.customer_id == customer_id)
        .order_by(Order.order_date.desc())
        .limit(3)
    ).all()

    open_tickets = session.scalars(
        select(SimulatedEmail)
        .where(
            SimulatedEmail.customer_id == customer_id,
            SimulatedEmail.status.in_(_OPEN_STATUSES),
        )
        .order_by(SimulatedEmail.received_at.desc())
        .limit(5)
    ).all()

    return {
        "customer": {
            "customer_id": customer.customer_id,
            "name": customer.name,
            "email": customer.email,
            "account_tier": customer.account_tier.value,
            "country": customer.country,
            "lifetime_value_usd": customer.lifetime_value_usd,
            "registration_date": customer.registration_date,
        },
        "recent_orders": [
            {
                "order_id": o.order_id,
                "product_name": o.product_name,
                "sku": o.sku,
                "status": o.status.value,
                "order_date": o.order_date,
                "estimated_delivery_date": o.estimated_delivery_date,
                "tracking_number": o.tracking_number,
                "amount_usd": o.amount_usd,
                "payment_status": o.payment_status.value,
            }
            for o in recent_orders
        ],
        "open_tickets": [
            {
                "email_id": e.email_id,
                "subject": e.subject,
                "status": e.status.value,
                "received_at": e.received_at,
            }
            for e in open_tickets
        ],
    }

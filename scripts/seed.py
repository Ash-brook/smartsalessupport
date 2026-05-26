"""Seed the database with synthetic customers, orders, and support emails.

Everything here is fake (no real CRM/inbox). Emails are generated to match the intent
distribution in PRD section 5.3, and each email stores its true intent in `intent_label`
so the eval harness can later score the classifier against ground truth.

Usage:
    python scripts/seed.py --customers 50 --orders-per-customer 3 --emails 200

Re-running wipes and regenerates the data. A fixed random seed makes runs reproducible.
"""

import argparse
import random
import sys
from datetime import timedelta
from pathlib import Path

# Allow `import backend...` when run as `python scripts/seed.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from faker import Faker  # noqa: E402

from backend.db import SessionLocal, engine  # noqa: E402
from backend.models import (  # noqa: E402
    AccountTier,
    AuditEvent,
    Customer,
    Draft,
    IntentLabel,
    Order,
    OrderStatus,
    PaymentStatus,
    SimulatedEmail,
)

# Target share of each intent (PRD 5.3). Must sum to 1.0.
INTENT_DISTRIBUTION = {
    IntentLabel.ORDER_STATUS: 0.30,
    IntentLabel.BILLING_QUERY: 0.25,
    IntentLabel.TECHNICAL_SUPPORT: 0.20,
    IntentLabel.REFUND_REQUEST: 0.15,
    IntentLabel.GENERAL_FAQ: 0.10,
}

PRODUCTS = [
    "AcmeCloud Pro",
    "Acme Smart Speaker",
    "Acme Fitness Band",
    "Acme Wireless Earbuds",
    "Acme 4K Webcam",
    "Acme Mechanical Keyboard",
    "Acme Standing Desk",
    "Acme Noise-Cancelling Headphones",
]

# Email templates per intent. {fields} are filled from the chosen customer/order.
# Several variants per intent give realistic variety in tone and detail.
TEMPLATES: dict[IntentLabel, list[tuple[str, str]]] = {
    IntentLabel.ORDER_STATUS: [
        (
            "Where is my order?",
            "Hi, I placed an order for the {product} on {order_date} (order {order_ref}) and it still "
            "hasn't arrived. The tracking says {tracking}. Can you tell me when it will be delivered?",
        ),
        (
            "Delivery delayed?",
            "Hello, my {product} order ({order_ref}) was supposed to arrive by {eta}. It's marked as "
            "{status}. What's going on?",
        ),
        (
            "Tracking not updating",
            "Hey team, the tracking number {tracking} for my {product} hasn't updated in days. Order {order_ref}. "
            "Please advise.",
        ),
    ],
    IntentLabel.BILLING_QUERY: [
        (
            "Why was I charged twice?",
            "I see two charges of ${amount} on my card for order {order_ref} ({product}). Did you bill me "
            "twice? Please check and refund the duplicate.",
        ),
        (
            "Question about my invoice",
            "Hi, I don't understand the ${amount} charge on my latest invoice for the {product}. Can you "
            "break down what I'm paying for?",
        ),
        (
            "Subscription charge",
            "I'm a {tier} customer and noticed an unexpected charge. My recent order was {order_ref}. "
            "Can you explain the billing?",
        ),
    ],
    IntentLabel.TECHNICAL_SUPPORT: [
        (
            "App keeps crashing on login",
            "Every time I try to log in to the {product} app it crashes immediately. I've reinstalled twice. "
            "I'm on the latest version. Help!",
        ),
        (
            "Device won't connect",
            "My {product} won't pair with my phone anymore after the last update. I've tried resetting it. "
            "What should I do?",
        ),
        (
            "Feature not working",
            "The sync feature on my {product} stopped working this week. Nothing I do fixes it. This is "
            "really frustrating as I use it daily.",
        ),
    ],
    IntentLabel.REFUND_REQUEST: [
        (
            "I want a refund for order {order_ref}",
            "The {product} I received (order {order_ref}, ${amount}) is faulty and I'd like a full refund. "
            "How do I return it?",
        ),
        (
            "Refund request",
            "I'm not happy with the {product} and want my money back. I paid ${amount}. Order {order_ref}. "
            "Please process a refund.",
        ),
        (
            "Return and refund",
            "Please refund order {order_ref}. The {product} didn't meet my expectations. I expect the ${amount} "
            "back to my original payment method.",
        ),
    ],
    IntentLabel.GENERAL_FAQ: [
        (
            "What are your business hours?",
            "Hi, what are your customer support hours? And do you offer phone support? Thanks!",
        ),
        (
            "Do you ship internationally?",
            "Hello, I'm based in {country} — do you ship here, and how long does delivery usually take?",
        ),
        (
            "How do I change my email?",
            "Quick question: how do I update the email address on my account? Can't find the setting.",
        ),
    ],
}


def _allocate_counts(total: int) -> dict[IntentLabel, int]:
    """Split `total` emails across intents per the distribution, fixing rounding drift."""
    counts = {intent: int(total * share) for intent, share in INTENT_DISTRIBUTION.items()}
    # Hand any leftover (from rounding down) to the largest category.
    leftover = total - sum(counts.values())
    counts[IntentLabel.ORDER_STATUS] += leftover
    return counts


def seed(n_customers: int, orders_per_customer: int, n_emails: int) -> None:
    fake = Faker()
    Faker.seed(42)
    random.seed(42)

    session = SessionLocal()
    try:
        # Wipe existing data so re-seeding is clean (child tables first for FK safety).
        for model in (AuditEvent, Draft, SimulatedEmail, Order, Customer):
            session.query(model).delete()
        session.commit()

        # --- Customers ---
        customers: list[Customer] = []
        for _ in range(n_customers):
            customers.append(
                Customer(
                    name=fake.name(),
                    email=fake.email(),
                    account_tier=random.choices(list(AccountTier), weights=[0.6, 0.3, 0.1])[0],
                    registration_date=fake.date_time_between(start_date="-2y", end_date="-1d"),
                    country=fake.country(),
                    open_tickets_count=random.randint(0, 4),
                    lifetime_value_usd=round(random.uniform(0, 5000), 2),
                )
            )
        session.add_all(customers)
        session.flush()  # assign customer_ids

        # --- Orders ---
        orders_by_customer: dict[str, list[Order]] = {}
        for customer in customers:
            cust_orders = []
            for _ in range(orders_per_customer):
                order_date = fake.date_time_between(start_date="-6M", end_date="-1d")
                status = random.choice(list(OrderStatus))
                order = Order(
                    customer_id=customer.customer_id,
                    product_name=random.choice(PRODUCTS),
                    sku=fake.bothify("SKU-####-??").upper(),
                    status=status,
                    order_date=order_date,
                    estimated_delivery_date=order_date + timedelta(days=random.randint(2, 10)),
                    tracking_number=fake.bothify("1Z###??####").upper(),
                    amount_usd=round(random.uniform(20, 600), 2),
                    payment_status=(
                        PaymentStatus.REFUNDED
                        if status == OrderStatus.REFUNDED
                        else random.choice(
                            [PaymentStatus.PAID, PaymentStatus.PAID, PaymentStatus.PENDING]
                        )
                    ),
                )
                cust_orders.append(order)
            orders_by_customer[customer.customer_id] = cust_orders
            session.add_all(cust_orders)
        session.flush()

        # --- Emails (per intent distribution) ---
        counts = _allocate_counts(n_emails)
        emails: list[SimulatedEmail] = []
        for intent, count in counts.items():
            for _ in range(count):
                customer = random.choice(customers)
                order = random.choice(orders_by_customer[customer.customer_id])
                subject_tpl, body_tpl = random.choice(TEMPLATES[intent])
                fields = {
                    "product": order.product_name,
                    "order_ref": "#" + order.order_id[:8].upper(),
                    "order_date": order.order_date.strftime("%d %b %Y"),
                    "eta": order.estimated_delivery_date.strftime("%d %b %Y"),
                    "status": order.status.value,
                    "tracking": order.tracking_number,
                    "amount": f"{order.amount_usd:.2f}",
                    "tier": customer.account_tier.value,
                    "country": customer.country,
                }
                emails.append(
                    SimulatedEmail(
                        customer_id=customer.customer_id,
                        subject=subject_tpl.format(**fields),
                        body_text=body_tpl.format(**fields),
                        received_at=fake.date_time_between(start_date="-14d", end_date="now"),
                        intent_label=intent,
                    )
                )
        random.shuffle(emails)  # mix intents so the inbox looks realistic
        session.add_all(emails)
        session.commit()

        # --- Summary ---
        print(
            f"Seeded: {len(customers)} customers, "
            f"{sum(len(o) for o in orders_by_customer.values())} orders, "
            f"{len(emails)} emails"
        )
        print("Email intent breakdown:")
        for intent, count in counts.items():
            pct = 100 * count / n_emails if n_emails else 0
            print(f"  {intent.value:<20} {count:>4}  ({pct:.0f}%)")
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SmartSupport synthetic data.")
    parser.add_argument("--customers", type=int, default=50)
    parser.add_argument("--orders-per-customer", type=int, default=3)
    parser.add_argument("--emails", type=int, default=200)
    args = parser.parse_args()

    # Make sure tables exist even if migrations haven't been run yet.
    import backend.models  # noqa: F401
    from backend.db import Base

    Base.metadata.create_all(engine)

    seed(args.customers, args.orders_per_customer, args.emails)


if __name__ == "__main__":
    main()

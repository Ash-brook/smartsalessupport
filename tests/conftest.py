"""Shared pytest fixtures.

Every test runs against a fresh in-memory SQLite database (StaticPool keeps the single
connection alive so the schema persists across sessions). We force MOCK_LLM on here — before
any backend module is imported — so the suite never touches the real API or needs a key, even
if the developer's .env has MOCK_LLM=false for live use.
"""

import os

os.environ["MOCK_LLM"] = "true"  # must be set before backend.config builds its settings

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401 - register tables on Base.metadata
from backend.db import Base, get_session
from backend.models import (
    AccountTier,
    Customer,
    IntentLabel,
    Order,
    OrderStatus,
    PaymentStatus,
    SimulatedEmail,
)


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    s = factory()
    yield s
    s.close()


@pytest.fixture
def seeded(session):
    """A small, deterministic dataset: a Free customer + an Enterprise customer, each with an
    order, plus one email per customer. Returns the created objects for assertions."""
    free = Customer(
        name="Free Fred",
        email="fred@example.com",
        account_tier=AccountTier.FREE,
        registration_date=datetime(2024, 1, 1),
        country="USA",
        open_tickets_count=1,
        lifetime_value_usd=120.0,
    )
    ent = Customer(
        name="Ent Erica",
        email="erica@bigco.com",
        account_tier=AccountTier.ENTERPRISE,
        registration_date=datetime(2023, 6, 1),
        country="UK",
        open_tickets_count=0,
        lifetime_value_usd=9000.0,
    )
    session.add_all([free, ent])
    session.flush()

    free_order = Order(
        customer_id=free.customer_id,
        product_name="Acme Smart Speaker",
        sku="SKU-1",
        status=OrderStatus.SHIPPED,
        order_date=datetime(2025, 1, 1),
        estimated_delivery_date=datetime(2025, 1, 8) + timedelta(days=1),
        tracking_number="1ZABC123",
        amount_usd=99.50,
        payment_status=PaymentStatus.PAID,
    )
    ent_order = Order(
        customer_id=ent.customer_id,
        product_name="AcmeCloud Pro",
        sku="SKU-2",
        status=OrderStatus.DELIVERED,
        order_date=datetime(2025, 2, 1),
        estimated_delivery_date=datetime(2025, 2, 5),
        tracking_number="1ZXYZ789",
        amount_usd=499.00,
        payment_status=PaymentStatus.PAID,
    )
    session.add_all([free_order, ent_order])

    faq_email = SimulatedEmail(
        customer_id=free.customer_id,
        subject="What are your hours?",
        body_text="Hi, what are your business hours? How do I reach you?",
        received_at=datetime(2025, 3, 1),
        intent_label=IntentLabel.GENERAL_FAQ,
    )
    refund_email = SimulatedEmail(
        customer_id=ent.customer_id,
        subject="Refund please",
        body_text="I want a refund for my order, this is unacceptable. Money back now.",
        received_at=datetime(2025, 3, 2),
        intent_label=IntentLabel.REFUND_REQUEST,
    )
    session.add_all([faq_email, refund_email])
    session.commit()

    return {
        "free": free,
        "ent": ent,
        "free_order": free_order,
        "ent_order": ent_order,
        "faq_email": faq_email,
        "refund_email": refund_email,
    }


@pytest.fixture
def client(session):
    """A FastAPI TestClient whose DB dependency is the in-memory test session."""
    from fastapi.testclient import TestClient

    from backend.main import app

    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()

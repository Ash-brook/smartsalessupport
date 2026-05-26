"""SQLAlchemy ORM models for SmartSupport (PRD section 5.1).

Five entities: Customer, Order, SimulatedEmail, Draft, AuditEvent.
All primary keys are UUID strings so they read cleanly in the UI and logs.
"""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


def _uuid() -> str:
    return str(uuid4())


def _enum(enum_cls: type[StrEnum]) -> Enum:
    """Store the human-readable .value (e.g. 'Order Status') in the DB, not the member
    name ('ORDER_STATUS'), so DB rows match LLM output and what the UI displays."""
    return Enum(enum_cls, values_callable=lambda e: [m.value for m in e])


# --- Enumerations ----------------------------------------------------------


class AccountTier(StrEnum):
    FREE = "Free"
    PRO = "Pro"
    ENTERPRISE = "Enterprise"


class OrderStatus(StrEnum):
    PENDING = "Pending"
    SHIPPED = "Shipped"
    DELIVERED = "Delivered"
    CANCELLED = "Cancelled"
    REFUNDED = "Refunded"


class PaymentStatus(StrEnum):
    PAID = "Paid"
    PENDING = "Pending"
    REFUNDED = "Refunded"
    FAILED = "Failed"


class IntentLabel(StrEnum):
    """The five support intent categories (PRD 5.3). Also used as classifier output."""

    BILLING_QUERY = "Billing Query"
    ORDER_STATUS = "Order Status"
    TECHNICAL_SUPPORT = "Technical Support"
    REFUND_REQUEST = "Refund Request"
    GENERAL_FAQ = "General FAQ"


class EmailStatus(StrEnum):
    UNPROCESSED = "Unprocessed"
    PROCESSING = "Processing"
    DRAFTED = "Drafted"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    SENT = "Sent"


class DraftStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"


class AuditAction(StrEnum):
    CLASSIFIED = "classified"
    DRAFTED = "drafted"
    AUTO_APPROVED = "auto_approved"
    APPROVED = "approved"
    EDITED_AND_APPROVED = "edited_and_approved"
    REJECTED = "rejected"


# Intents eligible for auto-reply (PRD 5.3). The rest always require human review.
AUTO_REPLY_ELIGIBLE = {
    IntentLabel.BILLING_QUERY,
    IntentLabel.ORDER_STATUS,
    IntentLabel.GENERAL_FAQ,
}


# --- Models ----------------------------------------------------------------


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    account_tier: Mapped[AccountTier] = mapped_column(_enum(AccountTier), nullable=False)
    registration_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)
    open_tickets_count: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_value_usd: Mapped[float] = mapped_column(Float, default=0.0)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
    emails: Mapped[list["SimulatedEmail"]] = relationship(back_populates="customer")


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    sku: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(_enum(OrderStatus), nullable=False)
    order_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    estimated_delivery_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String, nullable=True)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    payment_status: Mapped[PaymentStatus] = mapped_column(_enum(PaymentStatus), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="orders")


class SimulatedEmail(Base):
    __tablename__ = "emails"

    email_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Ground-truth label used by the eval harness; the classifier predicts this independently.
    intent_label: Mapped[IntentLabel] = mapped_column(_enum(IntentLabel), nullable=False)
    status: Mapped[EmailStatus] = mapped_column(
        _enum(EmailStatus), default=EmailStatus.UNPROCESSED, nullable=False
    )

    customer: Mapped[Customer] = relationship(back_populates="emails")
    drafts: Mapped[list["Draft"]] = relationship(back_populates="email")


class Draft(Base):
    __tablename__ = "drafts"

    draft_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email_id: Mapped[str] = mapped_column(ForeignKey("emails.email_id"), nullable=False)

    # Classification result carried alongside the draft for the review UI.
    intent: Mapped[IntentLabel | None] = mapped_column(_enum(IntentLabel), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Draft content.
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    final_body: Mapped[str | None] = mapped_column(Text, nullable=True)  # set if an agent edits

    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    model_used: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[DraftStatus] = mapped_column(
        _enum(DraftStatus), default=DraftStatus.PENDING, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    email: Mapped[SimulatedEmail] = relationship(back_populates="drafts")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    audit_event_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email_id: Mapped[str] = mapped_column(ForeignKey("emails.email_id"), nullable=False)
    draft_id: Mapped[str | None] = mapped_column(ForeignKey("drafts.draft_id"), nullable=True)
    action: Mapped[AuditAction] = mapped_column(_enum(AuditAction), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    edit_made: Mapped[bool] = mapped_column(Boolean, default=False)
    original_draft_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

"""Pydantic request/response models for the API (PRD section 9).

These define the JSON shapes the API accepts and returns. FastAPI uses them for
validation and to auto-generate the interactive docs at /docs.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

# --- /classify -------------------------------------------------------------


class ClassifyRequest(BaseModel):
    email_id: str
    body_text: str | None = None  # if omitted, the email body is loaded from the DB


class ClassifyResponse(BaseModel):
    intent: str
    confidence: float
    reasoning: str
    model_used: str
    latency_ms: float


# --- /customers/{id}/context ----------------------------------------------


class CustomerContext(BaseModel):
    customer_id: str
    name: str
    email: str
    account_tier: str
    country: str
    lifetime_value_usd: float
    registration_date: datetime


class OrderContext(BaseModel):
    order_id: str
    product_name: str
    sku: str
    status: str
    order_date: datetime
    estimated_delivery_date: datetime | None
    tracking_number: str | None
    amount_usd: float
    payment_status: str


class TicketContext(BaseModel):
    email_id: str
    subject: str
    status: str
    received_at: datetime


class ContextResponse(BaseModel):
    customer: CustomerContext
    recent_orders: list[OrderContext]
    open_tickets: list[TicketContext]


# --- /draft ----------------------------------------------------------------


class DraftRequest(BaseModel):
    email_id: str
    intent: str
    confidence: float
    # If omitted, the service builds context from the email's customer.
    customer_context: dict[str, Any] | None = None


class DraftResponse(BaseModel):
    draft_id: str
    subject: str
    body: str
    requires_human_review: bool
    flags: list[str]
    model_used: str
    latency_ms: float


# --- GET /drafts (review queue) -------------------------------------------


class DraftQueueItem(BaseModel):
    draft_id: str
    email_id: str
    customer_name: str
    subject: str
    intent: str | None
    confidence: float | None
    received_at: datetime
    status: str
    requires_human_review: bool  # True = HITL tag, False = was auto-approved
    flags: list[str]


class DraftQueueResponse(BaseModel):
    items: list[DraftQueueItem]
    page: int
    page_size: int
    total: int


# --- GET /drafts/{id} (3-panel review detail) -----------------------------


class OriginalEmail(BaseModel):
    email_id: str
    subject: str
    body_text: str
    received_at: datetime
    customer_name: str
    customer_email: str


class DraftDetail(BaseModel):
    draft_id: str
    subject: str
    body: str
    final_body: str | None
    intent: str | None
    confidence: float | None
    reasoning: str | None
    requires_human_review: bool
    flags: list[str]
    status: str
    model_used: str | None


class DraftDetailResponse(BaseModel):
    draft: DraftDetail
    email: OriginalEmail
    context: ContextResponse


# --- PATCH /drafts/{id}/action --------------------------------------------


class ActionRequest(BaseModel):
    action: str  # "approve" | "edit" | "reject"
    edited_body: str | None = None  # required when action == "edit"
    agent_id: str = "agent-1"
    rejection_reason: str | None = None  # required when action == "reject"


class ActionResponse(BaseModel):
    draft_id: str
    status: str
    updated_at: datetime
    audit_event_id: str


# --- GET /metrics (manager dashboard) -------------------------------------


class CategoryRow(BaseModel):
    intent: str
    count: int


class AuditLogRow(BaseModel):
    timestamp: datetime
    action: str
    agent_id: str | None
    customer_name: str
    subject: str


class ReasonRow(BaseModel):
    reason: str
    count: int


class MetricsResponse(BaseModel):
    total_emails: int
    processed: int
    auto_approved: int
    hitl: int
    pending: int
    sent: int
    rejected: int
    # Rates are 0.0–1.0 (PRD section 10).
    zero_touch_rate: float
    hitl_rate: float
    edit_rate: float
    rejection_rate: float
    category_breakdown: list[CategoryRow]
    audit_log: list[AuditLogRow]
    top_rejection_reasons: list[ReasonRow]

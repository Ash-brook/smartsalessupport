"""Draft review endpoints — the API behind the Agent Review UI (PRD sections 7.1, 7.4, 9).

GET   /api/v1/drafts                 paginated review queue (inbox)
GET   /api/v1/drafts/{id}            full 3-panel detail (email + draft + customer context)
PATCH /api/v1/drafts/{id}/action     approve / edit / reject, recording an audit event
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db import get_session
from backend.models import (
    AuditAction,
    AuditEvent,
    Customer,
    Draft,
    DraftStatus,
    EmailStatus,
    SimulatedEmail,
)
from backend.schemas import (
    ActionRequest,
    ActionResponse,
    ContextResponse,
    DraftDetail,
    DraftDetailResponse,
    DraftQueueItem,
    DraftQueueResponse,
    OriginalEmail,
)
from backend.services.enrich import build_context

router = APIRouter(prefix="/api/v1/drafts")
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=DraftQueueResponse)
def list_drafts(
    session: SessionDep,
    status: str = Query("pending", description="pending | approved | rejected | sent | all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> DraftQueueResponse:
    """The review queue. Oldest first (PRD 7.1). `status=all` shows everything for audit."""
    base = (
        select(Draft, SimulatedEmail, Customer)
        .join(SimulatedEmail, Draft.email_id == SimulatedEmail.email_id)
        .join(Customer, SimulatedEmail.customer_id == Customer.customer_id)
    )

    if status != "all":
        base = base.where(Draft.status == DraftStatus(status))

    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0

    rows = session.execute(
        base.order_by(SimulatedEmail.received_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        DraftQueueItem(
            draft_id=d.draft_id,
            email_id=e.email_id,
            customer_name=c.name,
            subject=e.subject,
            intent=d.intent.value if d.intent else None,
            confidence=d.confidence,
            received_at=e.received_at,
            status=d.status.value,
            requires_human_review=d.requires_human_review,
            flags=d.flags,
        )
        for d, e, c in rows
    ]
    return DraftQueueResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/{draft_id}", response_model=DraftDetailResponse)
def get_draft(draft_id: str, session: SessionDep) -> DraftDetailResponse:
    """Everything the 3-panel review screen needs in one call."""
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    email = session.get(SimulatedEmail, draft.email_id)
    customer = session.get(Customer, email.customer_id)
    context = build_context(session, email.customer_id) or {}

    return DraftDetailResponse(
        draft=DraftDetail(
            draft_id=draft.draft_id,
            subject=draft.subject,
            body=draft.body,
            final_body=draft.final_body,
            intent=draft.intent.value if draft.intent else None,
            confidence=draft.confidence,
            reasoning=draft.reasoning,
            requires_human_review=draft.requires_human_review,
            flags=draft.flags,
            status=draft.status.value,
            model_used=draft.model_used,
        ),
        email=OriginalEmail(
            email_id=email.email_id,
            subject=email.subject,
            body_text=email.body_text,
            received_at=email.received_at,
            customer_name=customer.name,
            customer_email=customer.email,
        ),
        context=ContextResponse(**context),
    )


@router.patch("/{draft_id}/action", response_model=ActionResponse)
def act_on_draft(draft_id: str, req: ActionRequest, session: SessionDep) -> ActionResponse:
    """Apply an agent's decision and write the audit event (PRD 7.4)."""
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    email = session.get(SimulatedEmail, draft.email_id)

    if req.action == "approve":
        draft.status = DraftStatus.SENT
        email.status = EmailStatus.SENT
        audit = AuditEvent(
            email_id=email.email_id,
            draft_id=draft.draft_id,
            action=AuditAction.APPROVED,
            agent_id=req.agent_id,
            edit_made=False,
        )
    elif req.action == "edit":
        if not req.edited_body:
            raise HTTPException(status_code=422, detail="edited_body required for action 'edit'")
        original = draft.body
        draft.final_body = req.edited_body
        draft.status = DraftStatus.SENT
        email.status = EmailStatus.SENT
        audit = AuditEvent(
            email_id=email.email_id,
            draft_id=draft.draft_id,
            action=AuditAction.EDITED_AND_APPROVED,
            agent_id=req.agent_id,
            edit_made=True,
            original_draft_body=original,
            final_body=req.edited_body,
        )
    elif req.action == "reject":
        if not req.rejection_reason:
            raise HTTPException(
                status_code=422, detail="rejection_reason required for action 'reject'"
            )
        draft.status = DraftStatus.REJECTED
        email.status = EmailStatus.REJECTED
        audit = AuditEvent(
            email_id=email.email_id,
            draft_id=draft.draft_id,
            action=AuditAction.REJECTED,
            agent_id=req.agent_id,
            rejection_reason=req.rejection_reason,
        )
    else:
        raise HTTPException(status_code=422, detail=f"unknown action '{req.action}'")

    session.add(audit)
    session.commit()
    session.refresh(audit)

    return ActionResponse(
        draft_id=draft.draft_id,
        status=draft.status.value,
        updated_at=audit.timestamp or datetime.now(),
        audit_event_id=audit.audit_event_id,
    )

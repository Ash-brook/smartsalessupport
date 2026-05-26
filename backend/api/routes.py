"""API route handlers (PRD section 9).

Thin wrappers over the service layer: they validate input, call a service, and shape the
response. The pipeline runner calls the same services directly, so logic lives in one place.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import get_session
from backend.models import SimulatedEmail
from backend.schemas import (
    ClassifyRequest,
    ClassifyResponse,
    ContextResponse,
    DraftRequest,
    DraftResponse,
    MetricsResponse,
)
from backend.services.draft import create_draft
from backend.services.enrich import build_context
from backend.services.llm_client import LLMClient
from backend.services.metrics import compute_metrics

router = APIRouter(prefix="/api/v1")

# One shared client for the process (reads MOCK_LLM / model from settings at startup).
llm = LLMClient()

# FastAPI dependency: a DB session injected per request.
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/classify", response_model=ClassifyResponse)
def classify(req: ClassifyRequest, session: SessionDep) -> ClassifyResponse:
    body = req.body_text
    if body is None:
        email = session.get(SimulatedEmail, req.email_id)
        if email is None:
            raise HTTPException(status_code=404, detail="email not found")
        body = email.body_text
    result = llm.classify(body)
    return ClassifyResponse(**result)


@router.get("/customers/{customer_id}/context", response_model=ContextResponse)
def customer_context(customer_id: str, session: SessionDep) -> ContextResponse:
    context = build_context(session, customer_id)
    if context is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return ContextResponse(**context)


@router.post("/draft", response_model=DraftResponse)
def draft(req: DraftRequest, session: SessionDep) -> DraftResponse:
    email = session.get(SimulatedEmail, req.email_id)
    if email is None:
        raise HTTPException(status_code=404, detail="email not found")

    context = req.customer_context
    if context is None:
        context = build_context(session, email.customer_id) or {}

    draft_row, meta = create_draft(
        session,
        llm,
        email,
        intent=req.intent,
        confidence=req.confidence,
        reasoning=None,
        context=context,
    )
    session.commit()
    return DraftResponse(
        draft_id=draft_row.draft_id,
        subject=draft_row.subject,
        body=draft_row.body,
        requires_human_review=draft_row.requires_human_review,
        flags=draft_row.flags,
        model_used=meta["model_used"],
        latency_ms=meta["latency_ms"],
    )


@router.get("/metrics", response_model=MetricsResponse)
def metrics(session: SessionDep) -> MetricsResponse:
    """KPIs for the manager dashboard (PRD section 10)."""
    return MetricsResponse(**compute_metrics(session))

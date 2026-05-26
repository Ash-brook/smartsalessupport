"""Mail intake endpoint — the drag-and-drop complaint feed (simulates a real inbox).

Agents never type issues; complaints only enter the system as uploaded files. Each file is
read, matched to a customer (or a new one is created from the sender), turned into an
Unprocessed email, and run straight through the pipeline so its AI draft lands in the queue.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db import get_session
from backend.models import AccountTier, Customer, Draft, EmailStatus, SimulatedEmail
from backend.schemas import IntakeResponse, IntakeResultItem
from backend.services.ingest import ingest_file
from backend.services.llm_client import LLMClient
from backend.services.pipeline import process_one

router = APIRouter(prefix="/api/v1/intake")
SessionDep = Annotated[Session, Depends(get_session)]
llm = LLMClient()


def _match_or_create_customer(
    session: Session, sender_email: str | None, sender_name: str | None
) -> Customer:
    """Find the sender in our 'CRM' by email, or register them as a new customer."""
    if sender_email:
        existing = (
            session.query(Customer)
            .filter(func.lower(Customer.email) == sender_email.lower())
            .first()
        )
        if existing:
            return existing

    name = sender_name or (sender_email.split("@")[0] if sender_email else "Unknown Sender")
    customer = Customer(
        name=name,
        email=sender_email or "unknown@example.com",
        account_tier=AccountTier.FREE,  # unknown senders start as Free tier
        registration_date=datetime.now(),
        country="Unknown",
        open_tickets_count=0,
        lifetime_value_usd=0.0,
    )
    session.add(customer)
    session.flush()
    return customer


@router.post("", response_model=IntakeResponse)
async def intake(session: SessionDep, files: Annotated[list[UploadFile], File()]) -> IntakeResponse:
    results: list[IntakeResultItem] = []
    for upload in files:
        try:
            content = await upload.read()
            extracted = ingest_file(upload.filename or "file", content, upload.content_type, llm)
            if not extracted.body.strip():
                raise ValueError("no readable complaint text found in file")

            customer = _match_or_create_customer(
                session, extracted.sender_email, extracted.sender_name
            )
            email = SimulatedEmail(
                customer_id=customer.customer_id,
                subject=extracted.subject[:200],
                body_text=extracted.body,
                received_at=datetime.now(),
                intent_label=None,  # real complaint — no ground-truth label
                status=EmailStatus.UNPROCESSED,
            )
            session.add(email)
            session.commit()

            result = process_one(session, llm, email.email_id)
            draft = (
                session.query(Draft)
                .filter_by(email_id=email.email_id)
                .order_by(Draft.created_at.desc())
                .first()
            )
            results.append(
                IntakeResultItem(
                    filename=upload.filename or "file",
                    source=extracted.source,
                    ok=True,
                    customer_name=customer.name,
                    intent=result.intent,
                    confidence=result.confidence,
                    outcome=result.outcome,
                    draft_id=draft.draft_id if draft else None,
                )
            )
        except Exception as err:  # noqa: BLE001 - report per-file, don't fail the whole batch
            session.rollback()
            results.append(
                IntakeResultItem(
                    filename=upload.filename or "file", source="error", ok=False, error=str(err)
                )
            )
    return IntakeResponse(results=results)

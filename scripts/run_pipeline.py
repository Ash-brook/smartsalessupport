"""Pipeline runner — the asyncio engine that drives emails through every stage (PRD 6.2).

For each Unprocessed email it: sanitises -> classifies -> enriches (if confident) -> drafts ->
routes (auto-reply vs. human review) -> records an audit event.

Usage:
    python scripts/run_pipeline.py --once          # process everything waiting, then exit
    python scripts/run_pipeline.py --limit 20       # process at most 20 emails, then exit
    python scripts/run_pipeline.py                  # poll forever (Ctrl+C to stop)

In live mode it throttles to PIPELINE_RATE_LIMIT_PER_MIN to stay within Gemini's free limits.
In mock mode there is no throttle, so test runs are instant.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow `import backend...` when run as `python scripts/run_pipeline.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import structlog  # noqa: E402

from backend.config import settings  # noqa: E402
from backend.db import SessionLocal  # noqa: E402
from backend.models import EmailStatus, SimulatedEmail  # noqa: E402
from backend.services.llm_client import LLMClient  # noqa: E402
from backend.services.pipeline import process_one  # noqa: E402

log = structlog.get_logger()

# Serialise DB writes so the async loop never races on the single SQLite file (PRD risk #5).
_db_lock = asyncio.Lock()


async def process_email(client: LLMClient, email_id: str) -> str:
    """Run one email through the full pipeline. Returns 'auto' or 'hitl'."""
    async with _db_lock:
        session = SessionLocal()
        try:
            result = process_one(session, client, email_id)
            log.info(
                "pipeline_processed",
                email_id=email_id[:8],
                intent=result.intent,
                confidence=result.confidence,
                outcome=result.outcome,
                reasons=result.reasons,
            )
            return result.outcome
        finally:
            session.close()


def _fetch_unprocessed_ids(limit: int) -> list[str]:
    session = SessionLocal()
    try:
        rows = (
            session.query(SimulatedEmail.email_id)
            .filter(SimulatedEmail.status == EmailStatus.UNPROCESSED)
            .order_by(SimulatedEmail.received_at)
            .limit(limit)
            .all()
        )
        return [r[0] for r in rows]
    finally:
        session.close()


async def run(once: bool, limit: int | None) -> None:
    client = LLMClient()
    throttle_s = 0.0 if client.mock else 60.0 / max(1, settings.pipeline_rate_limit_per_min)
    counts = {"auto": 0, "hitl": 0}
    processed = 0

    log.info("pipeline_start", mock=client.mock, throttle_s=throttle_s, once=once, limit=limit)

    while True:
        batch_size = (limit - processed) if limit else 100
        ids = _fetch_unprocessed_ids(batch_size) if batch_size > 0 else []

        for email_id in ids:
            outcome = await process_email(client, email_id)
            counts[outcome] += 1
            processed += 1
            if throttle_s:
                await asyncio.sleep(throttle_s)
            if limit and processed >= limit:
                break

        if (limit and processed >= limit) or (once and not ids):
            break
        if once and ids:
            continue  # keep draining until the inbox is empty
        await asyncio.sleep(settings.pipeline_poll_seconds)

    total = counts["auto"] + counts["hitl"]
    zero_touch = (100 * counts["auto"] / total) if total else 0
    log.info("pipeline_done", processed=total, auto=counts["auto"], hitl=counts["hitl"])
    print(
        f"\nProcessed {total} emails: {counts['auto']} auto-approved, "
        f"{counts['hitl']} sent to human review (zero-touch rate {zero_touch:.0f}%)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SmartSupport pipeline.")
    parser.add_argument("--once", action="store_true", help="drain the inbox once, then exit")
    parser.add_argument("--limit", type=int, default=None, help="process at most N emails")
    parser.add_argument("--quiet", action="store_true", help="suppress per-email log lines")
    args = parser.parse_args()

    if args.quiet:
        logging.disable(logging.INFO)

    asyncio.run(run(once=args.once or args.limit is not None, limit=args.limit))


if __name__ == "__main__":
    main()

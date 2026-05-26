"""Provider-agnostic LLM client for SmartSupport.

Two public methods drive the whole pipeline:
  - classify(email_body)              -> intent + confidence + reasoning
  - draft(intent, context, body)      -> a reply draft + self-assessed review flags

The real backend is Google Gemini (free tier). Setting MOCK_LLM=true in .env swaps in a
deterministic, no-network mock so tests and offline development never touch the API. The mock
is a real (if crude) keyword classifier + template drafter, so the rest of the pipeline behaves
realistically without a key.

Swapping providers later (Groq, Grok, OpenAI-compatible) means adding one more `_<provider>_*`
pair and a branch — the method signatures and return shapes stay the same.
"""

import json
import re
import time
from typing import Any

import structlog

from backend.config import settings
from backend.models import AUTO_REPLY_ELIGIBLE, IntentLabel

log = structlog.get_logger()

INTENT_VALUES = [i.value for i in IntentLabel]

# Words that should pull a draft into human review regardless of intent (PRD 7.2).
FLAG_KEYWORDS = {
    "legal": "legal_language",
    "lawyer": "legal_language",
    "sue": "legal_language",
    "complaint": "complaint",
    "unacceptable": "complaint",
    "terrible": "complaint",
    "refund": "refund_mentioned",
}

# Output-token budgets. Generous enough that the JSON answer is never truncated
# (Gemini 2.5 models also reserve some output tokens for internal "thinking").
CLASSIFY_MAX_TOKENS = 512
DRAFT_MAX_TOKENS = 1024


class LLMClient:
    """Single entry point for all LLM calls. Chooses real vs. mock based on settings."""

    def __init__(self) -> None:
        self.mock = settings.mock_llm
        self.model = settings.gemini_model
        self._gemini = None  # lazily created so mock mode needs no key

    # --- Public API --------------------------------------------------------

    def classify(self, email_body: str) -> dict[str, Any]:
        """Return {intent, confidence, reasoning, model_used, latency_ms}."""
        started = time.perf_counter()
        if self.mock:
            result = _mock_classify(email_body)
            model_used = "mock"
        else:
            result = self._gemini_classify(email_body)
            model_used = self.model
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        result.update(model_used=model_used, latency_ms=latency_ms)
        log.info(
            "llm_classify",
            stage="classify",
            model=model_used,
            latency_ms=latency_ms,
            intent=result.get("intent"),
        )
        return result

    def draft(self, intent: str, context: dict[str, Any], email_body: str) -> dict[str, Any]:
        """Return {subject, body, requires_human_review, flags, model_used, latency_ms}."""
        started = time.perf_counter()
        if self.mock:
            result = _mock_draft(intent, context, email_body)
            model_used = "mock"
        else:
            result = self._gemini_draft(intent, context, email_body)
            model_used = self.model
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        result.update(model_used=model_used, latency_ms=latency_ms)
        log.info(
            "llm_draft",
            stage="draft",
            model=model_used,
            latency_ms=latency_ms,
            flags=result.get("flags"),
        )
        return result

    # --- Gemini backend ----------------------------------------------------

    def _client(self):
        """Create the Gemini client on first use (so mock mode never imports/needs a key)."""
        if self._gemini is None:
            from google import genai

            if not settings.gemini_api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is empty. Set it in .env, or set MOCK_LLM=true for offline use."
                )
            self._gemini = genai.Client(api_key=settings.gemini_api_key)
        return self._gemini

    def _generate_json(
        self, *, system: str, user: str, temperature: float, max_tokens: int
    ) -> dict[str, Any]:
        """One JSON-mode Gemini call with retry/backoff on rate limits."""
        from google.genai import types

        config_kwargs: dict[str, Any] = dict(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        )
        # Gemini 2.5 Flash "thinks" by default, spending output tokens on hidden reasoning
        # we don't need for structured extraction. Turn it off so the whole budget goes to
        # the JSON answer (2.5 Pro requires a non-zero budget, so skip it there).
        if "2.5" in self.model and "pro" not in self.model.lower():
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        config = types.GenerateContentConfig(**config_kwargs)

        last_err: Exception | None = None
        for attempt in range(3):  # 3x exponential backoff (PRD 4.4)
            try:
                resp = self._client().models.generate_content(
                    model=self.model, contents=user, config=config
                )
                tokens = getattr(getattr(resp, "usage_metadata", None), "total_token_count", None)
                log.info("gemini_call", attempt=attempt + 1, tokens=tokens)
                return _parse_json(resp)
            except Exception as err:  # noqa: BLE001 - inspect message for rate limit
                last_err = err
                if "429" in str(err) or "RESOURCE_EXHAUSTED" in str(err):
                    wait = 2**attempt
                    log.warning("gemini_rate_limited", attempt=attempt + 1, wait_s=wait)
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError(f"Gemini call failed after retries: {last_err}")

    def _gemini_classify(self, email_body: str) -> dict[str, Any]:
        system = (
            "You are a customer-support email classifier. Read the email and assign exactly one "
            f"intent from this list: {INTENT_VALUES}. Respond ONLY as JSON with keys "
            '"intent" (one of the listed values), "confidence" (0.0-1.0), and "reasoning" '
            "(one short sentence)."
        )
        data = self._generate_json(
            system=system,
            user=email_body[:4000],
            temperature=0.1,
            max_tokens=CLASSIFY_MAX_TOKENS,
        )
        return {
            "intent": data.get("intent"),
            "confidence": float(data.get("confidence", 0.0)),
            "reasoning": data.get("reasoning", ""),
        }

    def _gemini_draft(
        self, intent: str, context: dict[str, Any], email_body: str
    ) -> dict[str, Any]:
        system = (
            "You are a helpful, professional customer-support agent for Acme. Write a concise, "
            "warm reply to the customer's email. Use ONLY facts present in the provided context; "
            "never invent order numbers, dates, or amounts. If you lack the information to fully "
            "resolve the issue, say a human will follow up and set requires_human_review to true. "
            'Respond ONLY as JSON with keys "subject" (string), "body" (string), '
            '"requires_human_review" (boolean), and "flags" (array of short strings).'
        )
        user = (
            f"Intent: {intent}\n"
            f"Customer context (JSON): {json.dumps(context, default=str)}\n"
            f"Customer email:\n{email_body[:4000]}"
        )
        data = self._generate_json(
            system=system,
            user=user,
            temperature=0.4,
            max_tokens=DRAFT_MAX_TOKENS,
        )
        return {
            "subject": data.get("subject", "Re: your enquiry"),
            "body": data.get("body", ""),
            "requires_human_review": bool(data.get("requires_human_review", False)),
            "flags": list(data.get("flags", [])),
        }

    # --- Vision (intake of images / scanned PDFs) --------------------------

    def extract_complaint(self, data: bytes, mime_type: str) -> dict[str, Any]:
        """Read a complaint from an image or scanned PDF.

        Returns {sender_email, subject, body}. Needs live Gemini; in mock mode it returns a
        placeholder so offline runs and tests don't crash.
        """
        if self.mock:
            return {
                "sender_email": None,
                "subject": "Scanned complaint (mock mode)",
                "body": "[mock] Reading images/scans needs live Gemini — set MOCK_LLM=false.",
            }
        return self._gemini_vision_extract(data, mime_type)

    def _gemini_vision_extract(self, data: bytes, mime_type: str) -> dict[str, Any]:
        from google.genai import types

        system = (
            "You are reading an image or scanned document of a customer support complaint "
            "or email. Extract the sender's email address if visible (else null), a short "
            "subject line, and the full complaint text. Respond ONLY as JSON with keys "
            '"sender_email", "subject", and "body".'
        )
        config_kwargs: dict[str, Any] = dict(
            system_instruction=system,
            temperature=0.1,
            max_output_tokens=1024,
            response_mime_type="application/json",
        )
        if "2.5" in self.model and "pro" not in self.model.lower():
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        part = types.Part.from_bytes(data=data, mime_type=mime_type)
        resp = self._client().models.generate_content(
            model=self.model,
            contents=[part],
            config=types.GenerateContentConfig(**config_kwargs),
        )
        parsed = _parse_json(resp)
        return {
            "sender_email": parsed.get("sender_email"),
            "subject": parsed.get("subject") or "Customer complaint",
            "body": parsed.get("body") or "",
        }


def _parse_json(resp: Any) -> dict[str, Any]:
    """Pull the JSON object out of a Gemini response, with a clear error if it's empty.

    Guards against the common 'truncated/empty output' failure and the occasional
    ```json ... ``` code fence some models add.
    """
    text = (getattr(resp, "text", None) or "").strip()
    if not text:
        reason = "unknown"
        candidates = getattr(resp, "candidates", None)
        if candidates:
            reason = getattr(candidates[0], "finish_reason", "unknown")
        raise RuntimeError(
            f"Gemini returned no text (finish_reason={reason}). "
            "If this is MAX_TOKENS, raise the token budget in llm_client.py."
        )
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    return json.loads(text)


# --- Mock backend (deterministic, no network) ------------------------------

# Keyword hints per intent for the mock classifier. Order matters: first strong match wins.
_MOCK_HINTS: list[tuple[IntentLabel, tuple[str, ...]]] = [
    (IntentLabel.REFUND_REQUEST, ("refund", "money back", "return")),
    (
        IntentLabel.TECHNICAL_SUPPORT,
        ("crash", "won't connect", "not working", "error", "bug", "pair"),
    ),
    (IntentLabel.BILLING_QUERY, ("charge", "charged", "invoice", "billing", "subscription", "$")),
    (IntentLabel.ORDER_STATUS, ("order", "delivery", "tracking", "shipped", "arrive", "where is")),
    (IntentLabel.GENERAL_FAQ, ("hours", "ship internationally", "change my email", "how do i")),
]


def _mock_classify(email_body: str) -> dict[str, Any]:
    text = email_body.lower()
    for intent, hints in _MOCK_HINTS:
        hit = sum(1 for h in hints if h in text)
        if hit:
            # More keyword hits -> higher confidence, capped below 1.0.
            confidence = min(0.95, 0.6 + 0.12 * hit)
            return {
                "intent": intent.value,
                "confidence": round(confidence, 2),
                "reasoning": f"[mock] matched {hit} keyword(s) for {intent.value}.",
            }
    return {
        "intent": IntentLabel.GENERAL_FAQ.value,
        "confidence": 0.5,
        "reasoning": "[mock] no strong keyword match; defaulting to General FAQ.",
    }


def _mock_draft(intent: str, context: dict[str, Any], email_body: str) -> dict[str, Any]:
    name = (context.get("customer") or {}).get("name", "there")
    flags: list[str] = []

    # Keyword-driven flags (mirrors the kind of self-flagging the real model does).
    text = email_body.lower()
    for kw, flag in FLAG_KEYWORDS.items():
        if kw in text and flag not in flags:
            flags.append(flag)

    # High-value refund flag (PRD 7.2: refund amount > $200).
    recent = context.get("recent_orders") or []
    if intent == IntentLabel.REFUND_REQUEST.value:
        max_amount = max((o.get("amount_usd", 0) for o in recent), default=0)
        if max_amount > 200:
            flags.append("high_refund_amount")

    needs_review = intent not in {i.value for i in AUTO_REPLY_ELIGIBLE} or bool(flags)

    body = (
        f"Hi {name},\n\n"
        f"Thanks for reaching out about your {intent.lower()}. "
        "We've received your message and are looking into it. "
        + (
            "A member of our team will follow up shortly with next steps.\n\n"
            if needs_review
            else "Here's what we found and how we can help right away.\n\n"
        )
        + "Best regards,\nAcme Support"
    )
    return {
        "subject": "Re: your enquiry",
        "body": body,
        "requires_human_review": needs_review,
        "flags": flags,
    }

"""Classification eval harness (PRD task #15, KPI 'Classification Accuracy').

Re-classifies every seeded email and compares the predicted intent to the ground-truth
`intent_label` stored at seed time. Prints overall accuracy plus a per-category breakdown.

Usage:
    python scripts/eval.py              # uses whatever LLM_PROVIDER / MOCK_LLM is in .env
    python scripts/eval.py --limit 50    # sample the first 50 emails (handy for live runs)

Note: in MOCK_LLM mode this measures the keyword mock (lower accuracy is expected). The
PRD's >=90% target applies to a live Gemini run.
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings  # noqa: E402
from backend.db import SessionLocal  # noqa: E402
from backend.models import SimulatedEmail  # noqa: E402
from backend.services.llm_client import LLMClient  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate classification accuracy.")
    parser.add_argument("--limit", type=int, default=None, help="evaluate at most N emails")
    args = parser.parse_args()

    client = LLMClient()
    session = SessionLocal()
    try:
        query = session.query(SimulatedEmail).order_by(SimulatedEmail.received_at)
        emails = query.limit(args.limit).all() if args.limit else query.all()

        if not emails:
            print("No emails found. Run seed.py first.")
            return

        correct = 0
        per_cat_total: dict[str, int] = defaultdict(int)
        per_cat_correct: dict[str, int] = defaultdict(int)

        for email in emails:
            true_label = email.intent_label.value
            predicted = client.classify(email.body_text)["intent"]
            per_cat_total[true_label] += 1
            if predicted == true_label:
                correct += 1
                per_cat_correct[true_label] += 1

        total = len(emails)
        mode = "MOCK" if client.mock else f"LIVE ({settings.gemini_model})"
        print(f"\nClassification eval — {mode} — {total} emails")
        print(f"Overall accuracy: {correct}/{total} = {100 * correct / total:.1f}%\n")
        print(f"{'Category':<20} {'Accuracy':>10}   N")
        print("-" * 40)
        for category in sorted(per_cat_total):
            n = per_cat_total[category]
            acc = 100 * per_cat_correct[category] / n
            print(f"{category:<20} {acc:>9.1f}%  {n:>3}")
    finally:
        session.close()


if __name__ == "__main__":
    main()

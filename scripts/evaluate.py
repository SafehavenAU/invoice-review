"""Check the four labelled sample reviews, including the unapproved variation."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from invoice_review.core import get_invoice_review


def main():
    cases = json.loads((ROOT / "eval/cases.json").read_text(encoding="utf-8"))
    over_supported = under_supported = wrong_evidence = count = failures = 0
    for case in cases:
        review = get_invoice_review(case["invoice_id"], case["scenario"])
        expected = case["expected_supported"]
        references = case["expected_evidence"]
        for line, amount, ids in zip(review["lines"], expected, references, strict=True):
            count += 1
            delta = line["supported_cents"] - amount
            over_supported += max(0, delta)
            under_supported += max(0, -delta)
            actual_ids = set(line["source_ids"]) - {review["invoice_source_id"]}
            mismatch = actual_ids != set(ids)
            wrong_evidence += int(mismatch)
            if delta or mismatch:
                failures += 1
                print(f"Mismatch: {case['invoice_id']} {case['scenario']} / {line['description']}")
    print(f"{len(cases)} fictional cases, {count} line decisions, {failures} mismatched decisions.")
    print(f"Excess supported cents: {over_supported}. Missed supported cents: {under_supported}.")
    print(f"Lines with mismatched evidence references: {wrong_evidence}.")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())

"""Build the self-contained invoice review walkthrough from the review engine."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invoice_review.core import get_invoice_review, get_source_record, list_invoices


def review_bundle(invoice_id, scenario):
    review = get_invoice_review(invoice_id, scenario=scenario)
    source_ids = {review["invoice_source_id"]}
    for line in review["lines"]:
        source_ids.update(line["source_ids"])
    return {
        "review": review,
        "sources": {
            source_id: get_source_record(source_id, scenario=scenario)
            for source_id in sorted(source_ids)
        },
    }


def main():
    invoices = {}
    for summary in list_invoices():
        invoice_id = summary["invoice_id"]
        invoices[invoice_id] = {"recorded": review_bundle(invoice_id, "recorded")}
        if invoice_id == "INV-1042":
            invoices[invoice_id]["draft"] = review_bundle(invoice_id, "variation_draft")

    # The JSON lives inside a script element. Escape tag delimiters even for fixtures.
    payload = json.dumps(invoices, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template_path = ROOT / "demo" / "index.template.html"
    template = template_path.read_text(encoding="utf-8")
    if template.count("{{REVIEW_DATA}}") != 1:
        raise ValueError("The HTML template must have exactly one data placeholder.")
    output = template_path.with_name("index.html")
    with output.open("w", encoding="utf-8", newline="\n") as target:
        target.write(template.replace("{{REVIEW_DATA}}", payload))
    print(f"Built {len(invoices)} invoice reviews in demo/index.html")


if __name__ == "__main__":
    main()
